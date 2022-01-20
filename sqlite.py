import mysql.connector
import common


class Table:
    NAME = 'threads'
    ID = 'id'
    COUNT = 'count'
    LAST_UPLOADED_AT = 'last_uploaded_at'


class ThreadDatabase:
    def __init__(self):
        user, pw, db_name = common.build_tuple('DB_INFO.pv')

        self.database = mysql.connector.connect(
            host="localhost",
            user=user,
            password=pw,
            database=db_name
        )

    def create_table(self):
        cursor = self.database.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS %s (" % Table.NAME +
            "%s INT UNSIGNED NOT NULL PRIMARY KEY, " % Table.ID +
            "%s INT UNSIGNED NOT NULL, " % Table.COUNT +
            "%s TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)" % Table.LAST_UPLOADED_AT
        )
        cursor.close()

    def drop_table(self):
        cursor = self.database.cursor()
        cursor.execute("DROP TABLE %s" % Table.NAME)
        cursor.close()

    def update_thread(self, thread_id: int, count: int):
        cursor = self.database.cursor()
        query = "INSERT INTO %s (%s, %s) VALUES (%s, %s) " % \
                (Table.NAME, Table.ID, Table.COUNT, str(thread_id), str(count)) + \
                "ON DUPLICATE KEY UPDATE %s = %s" % (Table.COUNT, str(count))
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def delete_old_threads(self) -> int:
        cursor = self.database.cursor()
        select_query = "SELECT %s FROM %s WHERE %s < DATE_SUB(NOW(), INTERVAL 70 DAY)" % \
                       (Table.ID, Table.NAME, Table.LAST_UPLOADED_AT)
        cursor.execute(select_query)
        counts = len(cursor.fetchall())

        delete_query = "DELETE FROM %s WHERE %s < DATE_SUB(NOW(), INTERVAL 70 DAY)" % \
                       (Table.NAME, Table.LAST_UPLOADED_AT)
        cursor.execute(delete_query)
        self.database.commit()
        cursor.close()
        return counts

    def get_reply_count(self, thread_id: int):
        cursor = self.database.cursor()
        # SELECT count FROM threads WHERE id=123456;
        query = "SELECT " + Table.COUNT + \
                " FROM " + Table.NAME + \
                " WHERE " + Table.ID + " = " + str(thread_id)
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        # Expected: result = [(237,)]
        if not result:
            return 0  # result = [] for a new thread_id
        else:
            try:
                return int(result[0][0])
            except Exception as e:
                print("The count of the thread undefined: " + str(e))
                return 0

    def close_connection(self):
        self.database.close()
