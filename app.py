import streamlit as st
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import pandas as pd

st.set_page_config(
    page_title="ニュース一括検索",
    page_icon="📰",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {max-width: 850px; padding-top: 1.2rem; padding-bottom: 3rem;}
.stButton button, .stDownloadButton button {width: 100%; min-height: 2.8rem;}
article {overflow-wrap: anywhere;}
</style>
""", unsafe_allow_html=True)

st.title("📰 ニュース一括検索")
st.caption("Yahoo!ニュース・NHKニュースから、キーワードに関連する記事をまとめて探します。")

with st.expander("検索条件", expanded=True):
    raw_keywords = st.text_area(
        "キーワード（1行に1つ）",
        placeholder="生成AI\n半導体\n中国",
        height=120,
        help="複数キーワードのどれかを含む記事を検索します。",
    )
    period_label = st.selectbox("掲載期間", ["過去24時間", "過去3日間", "過去7日間"], index=0)
    period_hours = {"過去24時間": 24, "過去3日間": 72, "過去7日間": 168}[period_label]
    sources = st.multiselect(
        "検索するニュースサイト",
        ["Yahoo!ニュース", "NHKニュース"],
        default=["Yahoo!ニュース", "NHKニュース"],
    )
    search_button = st.button("🔎 一括検索", type="primary")

def get_feed(keyword, site):
    # Google News RSS is used as a discovery index. Search each publisher separately.
    domain = {
        "Yahoo!ニュース": "news.yahoo.co.jp",
        "NHKニュース": "nhk.or.jp",
    }[site]
    query = f'site:{domain} "{keyword}" when:{ "1d" if period_hours == 24 else ("3d" if period_hours == 72 else "7d") }'
    url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=ja&gl=JP&ceid=JP:ja"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NewsSearch/1.0)"},
        timeout=20,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=period_hours)
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
        except Exception:
            continue
        if not title or not link or published < cutoff:
            continue
        source_node = item.find("source")
        source_name = (source_node.text or "").strip() if source_node is not None else ""
        # The query is scoped to one publisher; source label is still shown as the requested publisher.
        rows.append({
            "記事タイトル": title,
            "掲載元": site,
            "公開日時": published.astimezone().strftime("%Y-%m-%d %H:%M"),
            "キーワード": keyword,
            "URL": link,
            "_published": published,
            "_source_label": source_name,
        })
    return rows

if search_button:
    keywords = list(dict.fromkeys(k.strip() for k in raw_keywords.splitlines() if k.strip()))
    if not keywords:
        st.warning("キーワードを1つ以上入力してください。")
    elif not sources:
        st.warning("検索するニュースサイトを少なくとも1つ選んでください。")
    else:
        all_rows, errors = [], []
        total = len(keywords) * len(sources)
        progress = st.progress(0, text="検索を開始しています…")
        done = 0
        for keyword in keywords:
            for source in sources:
                done += 1
                progress.progress(done / total, text=f"検索中：{keyword}（{source}）")
                try:
                    all_rows.extend(get_feed(keyword, source))
                except Exception as exc:
                    errors.append(f"{keyword} / {source}: {exc}")
        progress.empty()

        if errors:
            with st.expander("一部の検索に失敗しました"):
                st.write("通信状況や検索サービス側の制限により、取得できない場合があります。")
                for error in errors:
                    st.code(error)

        if not all_rows:
            st.info("該当記事が見つかりませんでした。キーワードを変えるか、期間を広げて再検索してください。")
        else:
            df = pd.DataFrame(all_rows)
            df = df.sort_values("_published", ascending=False)
            df = df.drop_duplicates(subset=["URL"])
            st.success(f"{len(df)}件の記事が見つかりました")
            c1, c2 = st.columns(2)
            c1.metric("Yahoo!ニュース", int((df["掲載元"] == "Yahoo!ニュース").sum()))
            c2.metric("NHKニュース", int((df["掲載元"] == "NHKニュース").sum()))

            for _, row in df.iterrows():
                st.markdown(f"**[{row['記事タイトル']}]({row['URL']})**")
                st.caption(f"{row['掲載元']} · {row['公開日時']} · 検索語：{row['キーワード']}")
                st.divider()

            export_df = df[["記事タイトル", "掲載元", "公開日時", "キーワード", "URL"]]
            st.download_button(
                "📥 結果をCSVで保存",
                data=export_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="news_search_results.csv",
                mime="text/csv",
            )
else:
    st.info("キーワードを1行に1つ入力して、「一括検索」を押してください。")
    st.markdown("**例**")
    st.code("生成AI\n半導体\n中国\nサイバー攻撃")
    st.caption("検索は Google ニュースのRSS検索を利用しています。検索対象のサイトを指定して記事を探します。")

with st.expander("このツールについて"):
    st.write("""
- 検索対象：Yahoo!ニュース、NHKニュース
- 条件：入力したキーワードのいずれかに関連する記事（キーワードごとに検索して統合）
- 期間：過去24時間／3日間／7日間
- 表示：記事タイトル、掲載元、公開日時、リンク
- 同じ記事が複数キーワードで見つかった場合は、URLで重複をまとめます。

注意：Google ニュースのRSSを検索用インデックスとして利用するため、記事の完全な網羅性は保証されません。検索結果のURLはGoogleニュース経由になる場合があります。外部サービスの仕様変更やアクセス制限で一時的に検索できないことがあります。
""")
