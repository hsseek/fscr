import mysql.connector


class Table:
    NAME = 'threads'
    C0 = 'id'
    C1 = 'count'


class ThreadDb:
    def __init__(self):
        def read_from_file(path: str):
            with open(path) as f:
                return f.read().strip('\n')

        self.thread_db = mysql.connector.connect(
            host="localhost",
            user=read_from_file('db_user.pv'),
            password=read_from_file('db_password.pv'),
            database=read_from_file('db_name.pv')
        )

    def create_table(self):
        thread_cursor = self.thread_db.cursor()
        thread_cursor.execute("CREATE TABLE IF NOT EXISTS " + Table.NAME + " ("
                              + Table.C0 + " INT PRIMARY KEY, "
                              + Table.C1 + " INT"
                                           ")")
        thread_cursor.close()

    def drop_table(self, table_name: str):
        thread_cursor = self.thread_db.cursor()
        thread_cursor.execute("DROP TABLE " + table_name)
        thread_cursor.close()

    # Compare the current number of replies with the last.
    def get_reply_count_not_scanned(self, thread_id: int, current_count: int) -> int:
        last_count = self.__get_reply_count(thread_id)

        if last_count == 0:
            self.insert_thread(thread_id, current_count)
        else:
            self.update_thread(thread_id, current_count)
        return current_count - last_count

    def insert_thread(self, thread_id: int, count: int):
        thread_cursor = self.thread_db.cursor()
        query = "INSERT INTO " + Table.NAME + \
                " (" + Table.C0 + ", " + Table.C1 + ")" \
                                                    "VALUES (" + str(thread_id) + ", " + str(count) + ")"
        thread_cursor.execute(query)
        self.thread_db.commit()
        thread_cursor.close()

    def update_thread(self, thread_id: int, count: int):
        thread_cursor = self.thread_db.cursor()
        query = "UPDATE " + Table.NAME + \
                " SET " + Table.C1 + " = " + str(count) + \
                " WHERE " + Table.C0 + " = " + str(thread_id)
        thread_cursor.execute(query)
        self.thread_db.commit()
        thread_cursor.close()

    def __get_reply_count(self, thread_id: int):
        thread_cursor = self.thread_db.cursor()
        # SELECT count FROM threads WHERE id=123456;
        query = "SELECT " + Table.C1 + \
                " FROM " + Table.NAME + \
                " WHERE " + Table.C0 + " = " + str(thread_id)
        thread_cursor.execute(query)
        result = thread_cursor.fetchall()
        thread_cursor.close()
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

    def close_connection(self):
        self.thread_db.close()
