from app import app
from flask_script import Manager, Server

manage = Manager(app)
# manage.add_command("runserver", Server(
#     host = '0.0.0.0')
# )

if __name__ == "__main__":
    manage.run()
