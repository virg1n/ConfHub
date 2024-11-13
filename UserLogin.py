from flask_login import UserMixin

class UserLogin(UserMixin):
    def fromDB(self, user_id, db):
        self.__user = db.getUserByID(user_id)
        return self

    def create(self, user):
        self.__user = user
        return self

    def get_id(self):
        return str(self.__user['id'])

    @property
    def name(self):
        return self.__user['name']
