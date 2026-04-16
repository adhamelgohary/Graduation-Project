FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static/uploads/profile_pics static/uploads/doctor_docs static/uploads/department_images \
    static/uploads/condition_images static/uploads/condition_videos static/uploads/chat_attachments \
    static/uploads/patient_reports static/uploads/vaccine_category_images

ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=54321
ENV FLASK_DEBUG=False

EXPOSE 54321

CMD ["python", "app.py"]