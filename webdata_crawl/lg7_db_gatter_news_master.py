import mariadb
import sys

try:
    conn_src = mariadb.connect(
        user="lguplus7",
        password="lg7p@ssw0rd~!",
        host="192.168.14.38",
        port=3310,
        database="news"
    )
    conn_tar = mariadb.connect(
        user="lguplus7",
        password="lg7p@ssw0rd~!",
        host="localhost",
        port=3310,
        database="news"
    )
except mariadb.Error as e:
    print(f"Error connecting to MariaDB Platform: {e}")
    sys.exit(1)

src_cur = conn_src.cursor()
tar_cur = conn_tar.cursor()

src_cur.execute("select seq_no, news_title, news_desc, news_url, news_update from news_master")
res = src_cur.fetchall()
print(f'fetched {len(res)} records')
for record in res:
    print(f'seq_no = {record[0]}')
    print(f'news_title = {record[1]}')
    print(f'news_desc = {record[2]}')
    print(f'news_url = {record[3]}')
    print(f'news_update = {record[4]}')

    tar_cur.execute("select * from news_master where news_url = ?", (record[3],))
    tar_res = tar_cur.fetchone()
    if tar_res is None or len(tar_res) == 0:
        print(f'no my news_master record found for news_url = {record[3]}')
        tar_cur.execute("insert into news_master(news_title, news_desc, news_url, news_update) values (?,?,?,?)", (record[1],record[2],record[3],record[4]))
        conn_tar.commit()
    else:
        print(f'my news_master record found for news_url = {record[3]}')
