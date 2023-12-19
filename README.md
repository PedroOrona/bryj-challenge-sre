# bryj-challenge-sre

This is a Python application wich parses metrics, trigger alarms and also make specific actions depending on the target metric. It collects information/metrics from cAdvisor container, which is an application that provides resource usage and performance for running containers.

We also provide a Dockerfile which converts the Python application into a container based application.

## Requirements

- Python 3.9 (Download [here](https://www.python.org/downloads/))
- Docker (Installation guide [here](https://docs.docker.com/get-docker/))

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

4. Run the application:

```bash
python src/app.py
```

## Build and run the docker container

1. Build the docker image:
```bash
docker build . -t bryj
```

2. Create and start the container:

```bash
docker run -d --name bryj-metrics-app bryj
```

3. Check the logs:
```bash
docker logs -f bryj-metrics-app
```