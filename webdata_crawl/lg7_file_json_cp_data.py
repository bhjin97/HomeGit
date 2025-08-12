import mariadb
import sys
import os
import json

try:
    conn_tar = mariadb.connect(
        user="lguplus7",
        password="lg7p@ssw0rd~!",
        host="localhost",
        port=3310,
        database="cp_data"
    )
except mariadb.Error as e:
    print(f"Error connecting to MariaDB Platform: {e}")
    sys.exit(1)

tar_cur = conn_tar.cursor()

json_path = 'c:/data/ts_data'
# 경로 내에 파일을 모두 불러옴
file_list = os.listdir( json_path )
#json 확장자를 가진 파일로 새로운 리스트 생성
json_file_list = [file for file in file_list if file.endswith('.json')]

for json_file_name in json_file_list:
    print(f'json_file_name = {json_path}/{json_file_name}')

    with open(json_path + '/' + json_file_name, encoding='UTF8') as json_file:
        json_reader = json_file.read()
        json_dic = json.loads( json_reader )

    document_id = json_dic['info'][0]['document_id']
    print( f"document_id = {document_id}")
    contents_title = json_dic['annotation'][0]['contents_title']
    print( f"contents_title = {contents_title}")
    sentence_id = json_dic['annotation'][0]['contents'][0]['sentence_id']
    print( f"sentence_id = {sentence_id}")
    sentence_title = json_dic['annotation'][0]['contents'][0]['sentence_title']
    print( f"sentence_title = {sentence_title}")
    sentence_text = json_dic['annotation'][0]['contents'][0]['sentence_text']
    print( f"sentence_text = {sentence_text}")

    tar_cur.execute(
        "insert into tb_cp(document_id, contents_title, sentence_id, sentence_title, sentence_text, json_data, create_dt ) values (?,?,?,?,?,?,now())",
        (document_id, contents_title, sentence_id, sentence_title, sentence_text, json.dumps(json_dic ) ))
    conn_tar.commit()
    print('insert into cp_data done')
