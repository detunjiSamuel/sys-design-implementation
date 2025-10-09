
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





def main():
    print("Hello from etl-live-stream-youtube!")


if __name__ == "__main__":
    main()
