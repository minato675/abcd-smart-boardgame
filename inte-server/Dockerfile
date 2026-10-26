FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

COPY ./*.jar app.jar

EXPOSE 8111

ENTRYPOINT ["java", "-Dserver.port=8111", "-jar", "app.jar"]
