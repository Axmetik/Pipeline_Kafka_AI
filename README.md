start docker containers ***docker compose -f docker/docker-compose.yml up -d***  

shut down docker containers ***docker compose -f docker/docker-compose.yml down -v***

get docker images ***docker compose -f docker/docker-compose.yml pull***

show docker containers ***docker ps***  

logs of docker container ***docker logs <docker-container-name> --tail=100***  

run producer ***python -m producer.iot_producer***

run consumer ***python -m consumer.iot_consumer***