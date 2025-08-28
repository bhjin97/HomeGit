# import Library
from playwright.sync_api import sync_playwright
import mariadb
from bs4 import BeautifulSoup
import sys, time

# try connection with mariadb
try:
    conn = mariadb.connect(
        host = "localhost",
        username = "lguplus7",
        password = "lg7p@ssw0rd~!",
        port = 3310,
        database = "cp_data"
    )

except mariadb.Error as e:
    print(f'mariadb error ocurred : {e}')
    sys.exit(1)

# preparing source
cur = conn.cursor()

scrap_url_list = []
scrap_url_list.append(['http://url~', -1])

source_type = 0

duplicate_yn = 'Y'
duplicate_max = 30

# playwright
with sync_playwright() as p:
    current_list_pos = 0
    current_page = 1
    
    browser = p.firefox.launch(headless=True)
    main_page = browser.new_page()

    while True:
        try:
            time.sleep(5)
            main_page.goto(f'{scrap_url_list[current_list_pos][0]}{current_page}')
        except TimeoutError as te:
            print(f'Error browser: {te}')
            browser.close()
            browser = p.firefox.launch(headless=True)
            main_page = browser.new_page()
            time.sleep(60)
            main_page.goto(f'{scrap_url_list[current_list_pos][0]}{current_page}')            
        
        time.sleep(5)

        print('list page: ' main_page.url) 

        content = main_page.content()
        soup = BeautifulSoup(content , 'html_parser')