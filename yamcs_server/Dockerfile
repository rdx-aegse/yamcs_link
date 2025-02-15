FROM ubuntu:24.10

WORKDIR /yamcs_cont

RUN apt update
RUN apt install git -y
#TO compile YAMCS via maven
RUN apt install openjdk-21-jdk -y
#To convert CSVs to XLS
RUN apt install gnumeric -y

#Install YAMCS
RUN apt install -y maven 
RUN git clone https://github.com/yamcs/quickstart.git yamcs_repo

#Too run YAML generator script
RUN apt install python3 python-is-python3 -y

#Copy the host's custom code over
COPY ./src /yamcs_cont/yamcs_repo/src/main/
COPY ./scripts /scripts/

RUN chmod +x /scripts/*

WORKDIR /yamcs_cont/yamcs_repo

# Download dependencies and compile to avoid doing that every time
RUN mvn dependency:go-offline compile

WORKDIR /yamcs_cont/

CMD ["/scripts/run.sh"]
