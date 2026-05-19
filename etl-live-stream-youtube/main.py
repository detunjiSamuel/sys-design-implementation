
"""
Goal :


 Goal is to build an ETL pipeline that can multiple hadnle live streaming data.

 Steps:

    Comment service:
        Get the last comments from stream
        Push to kafka topic for processing

    Processing service:
        Get the comments from kafka topic
        Process the comments in Apache Spark
        Push the processed comments in batch to mongoDB

    Comment Analytics service:
        Listen to the processed comments in mongoDB
        and send to a frontend service


"""


import structlog

from YTComments.main import main as comments_main
from sparkAnalysis.main import main as spark_main

log = structlog.get_logger(__name__)


def main():
    log.info("service_starting")


if __name__ == "__main__":
    # comments_main()
    spark_main()
