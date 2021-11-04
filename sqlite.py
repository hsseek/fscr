import mysql.connector


class Table:
    NAME = 'threads'
    ID = 'id'
    COUNT = 'count'
    LAST_UPLOADED_AT = 'last_uploaded_at'


class ThreadDb:
    def __init__(self):
        def read_from_file(path: str):
            with open(path) as f:
                return f.read().strip('\n')

        self.database = mysql.connector.connect(
            host="localhost",
            user=read_from_file('db_user.pv'),
            password=read_from_file('db_password.pv'),
            database=read_from_file('db_name.pv')
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

    # Compare the current number of replies with the last.
    def get_reply_count_not_scanned(self, thread_id: int, current_count: int) -> int:
        last_count = self.__get_reply_count(thread_id)

        if last_count == 0:
            self.insert_thread(thread_id, current_count)
        else:
            self.update_thread(thread_id, current_count)
        return current_count - last_count

    def insert_thread(self, thread_id: int, count: int):
        cursor = self.database.cursor()
        query = "INSERT INTO " + Table.NAME + \
                " (" + Table.ID + ", " + Table.COUNT + ")" \
                                                       " VALUES (" + str(thread_id) + ", " + str(count) + ")"
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def delete_thread(self, thread_id: int):
        cursor = self.database.cursor()
        query = "DELETE FROM " + Table.NAME + \
                " WHERE " + Table.ID + "=" + str(thread_id)
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def delete_old_threads(self) -> int:
        cursor = self.database.cursor()
        select_query = "SELECT %s FROM %s WHERE %s < DATE_SUB(NOW(), INTERVAL 60 DAY)" % \
                       (Table.ID, Table.NAME, Table.LAST_UPLOADED_AT)
        cursor.execute(select_query)
        counts = len(cursor.fetchall())

        delete_query = "DELETE FROM %s WHERE %s < DATE_SUB(NOW(), INTERVAL 60 DAY)" % \
                       (Table.NAME, Table.LAST_UPLOADED_AT)
        cursor.execute(delete_query)
        self.database.commit()
        cursor.close()
        return counts

    def update_thread(self, thread_id: int, count: int):
        cursor = self.database.cursor()
        query = "UPDATE " + Table.NAME + \
                " SET " + Table.COUNT + " = " + str(count) + \
                " WHERE " + Table.ID + " = " + str(thread_id)
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def __get_reply_count(self, thread_id: int):
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
                # 아무것도 return 하지 않으면 get_count() 에서 값 받아야 하는 함수는 어떻게 거동?: return None
                return 0

    def fetch_finished(self) -> []:
        cursor = self.database.cursor()
        query = "SELECT %s FROM %s WHERE %s=300" % (Table.ID, Table.NAME, Table.COUNT)
        cursor.execute(query)
        tuples = cursor.fetchall()
        cursor.close()
        threads = []
        for i, thread_no in enumerate(tuples):
            threads.append(tuples[i][0])
        return threads

    def close_connection(self):
        self.database.close()
