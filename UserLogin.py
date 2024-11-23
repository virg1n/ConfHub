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
        return self.__user['username']  # Changed from 'name' to 'username'

    @property
    def first_name(self):
        return self.__user['first_name']

    @property
    def last_name(self):
        return self.__user['last_name']

    @property
    def email(self):
        return self.__user['email']

    # Add properties for optional fields as needed
    @property
    def organization(self):
        return self.__user['organization']

    @property
    def country(self):
        return self.__user['country']

    @property
    def city(self):
        return self.__user['city']

    @property
    def address(self):
        return self.__user['address']

    @property
    def phone_number(self):
        return self.__user['phone_number']
