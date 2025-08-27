from passlib.context import CryptContext


class Hash:
    def __init__(self):
        # Initialize the password context with bcrypt hashing algorithm
        # and set deprecated to auto to use the latest version
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def verify_password(self, plain_password, hashed_password):
        return self.pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password):
        return self.pwd_context.hash(password)
