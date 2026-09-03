import sqlite3, json

conn = sqlite3.connect(r'c:\Users\HP\OneDrive\Desktop\Kaibridge\EasyBridge\easybridge\core\base_template.eprj')
c = conn.cursor()
c.execute('SELECT title, dataStr FROM components')
for title, data in c.fetchall():
    for line in data.splitlines():
        if line.startswith('["PART"'):
            parsed = json.loads(line)
            print(f"{title} -> PART: {parsed[1]}")
            break
