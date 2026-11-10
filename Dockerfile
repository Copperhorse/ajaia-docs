# Builds the app as a container, for any host that runs Docker (for example a Hugging Face Space, which expects
# port 7860 and a non-root user). It is not used on Vercel, which runs the app without Docker.
FROM python:3.14-slim

# Hugging Face Spaces runs containers as user 1000, so use that user instead of root.
RUN useradd --create-home --uid 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}"
WORKDIR /home/user/app

# Install the exact pinned libraries first, so this layer is reused when only the code changes.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the app needs at run time. Never .env: secrets come from the host's environment variables.
COPY --chown=user app ./app
COPY --chown=user static ./static

# Settings come from environment variables: DATABASE_URL, SECRET_KEY, SEED_PASSWORD, COOKIE_SECURE.
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
