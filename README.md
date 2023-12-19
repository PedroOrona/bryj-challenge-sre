# BRYJ SRE challenge

This is a Python application wich parses metrics, trigger alarms and also make specific actions depending on the target metric. It collects information/metrics from cAdvisor container, which is an application that provides resource usage and performance for running containers.

We also provide a Dockerfile which converts the Python application into a container based application.

## Requirements

- Python 3.9 (Download [here](https://www.python.org/downloads/))
- Docker (Installation guide [here](https://docs.docker.com/get-docker/))
- AWS CLI configured (Installation guide [here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))

## Development

1. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install the python requirements:

```bash
pip install -r src/requirements.txt
```

3. Run the Docker Compose, this will initialize two containers with the following base images, redis and cAdvisor, and check that they are running properly:

```bash
docker-compose up -d
docker ps
```

you can  also check the logs with:
```bash
docker logs -f redis
docker logs -f cadvisor
```

4. Define the AWS Profile to be used (Optional):

If you don't want to use the default profile, add the `AWS_CONFIG_PROFILE_NAME` environment variable to the `/src/.env` file with the desired profile name as its value. 

5. Run the application:

```bash
python src/app.py
```

## Build and run the docker container

1. Build the docker image:
```bash
docker build . -t bryj
```

2. Create and start the container:

In case you are running on an EC2 that has an IAM Role attached to it, simply run:
```bash
docker run -d --name bryj-metrics-app bryj
```

or if you are running locally and has aws configured with a profile, run the following:

```bash
docker run -d -v $HOME/.aws/credentials:/root/.aws/credentials:ro --name bryj-metrics-app bryj
```

If you want to use an specific profile instead of the default one, first, add the `AWS_CONFIG_PROFILE_NAME` environment variable to the `/src/.env-docker` file with the desired profile name as its value. And then run the previous command.

3. Check the logs:
```bash
docker logs -f bryj-metrics-app
```