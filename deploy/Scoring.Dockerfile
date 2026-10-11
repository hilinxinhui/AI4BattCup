FROM ai4batt/codabench:v1.33
# The compute worker supplies the full command; no shell entrypoint is needed.
ENTRYPOINT []
CMD ["python", "--version"]
