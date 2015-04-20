import os


class Config(object):
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    SECRET_KEY = "change-me"
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://csshepard:Married2Rene!@localhost/nscdb')
    CELERY_BROKER_URL = os.getenv('CLOUDAMQP_URL', 'amqp://guest@localhost')
    CELERY_RESULT_BACKEND = os.getenv('CLOUDAMQP_URL', 'amqp://guest@localhost')
    CELERY_TASK_SERIALIZER = 'json'


class ProductionConfig(Config):
    DEBUG = False


class StagingConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class DevelopmentConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class TestingConfig(Config):
    TESTING = True

