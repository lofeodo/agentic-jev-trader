# The Python image: one image for every Python piece (spec appendix 10, section 3), each
# started by its own command:
#   memory server   python -m jev_trader.memory serve
#   API             python -m jev_trader.api serve
#   sim job         python -m jev_trader.sim resume <sim id>
#   dataset build   python -m jev_trader.dataset build <settings file>
# Built and loaded into kind by `conda run -n agentic-jev-trader python infra/images.py build`, tagged with the git commit.
# It never holds a secret: .dockerignore keeps .env, keys and saved tables out.
#
# Skeleton: the code and the pinned dependencies arrive with the slice's images ticket (#198).
FROM python:3.12-slim
CMD ["python", "-c", "print('the Python image is not built yet')"]
