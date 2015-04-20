import os


class Config(object):
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    SECRET_KEY = "change-me"
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'postgresql://localhost/nscdb')
    CELERY_BROKER_URL = os.getenv('REDISGREEN_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.getenv('REDISGREEN_URL', 'redis://localhost:6379/0')


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

