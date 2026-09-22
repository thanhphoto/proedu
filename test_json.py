import json
from django.template import Template, Context
from django.conf import settings
if not settings.configured:
    settings.configure(TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates'}])

data = {"code": [{"correct": 1, "type": "SINGLE"}]}
data_json = json.dumps(data)

t = Template("const data = JSON.parse('{{ data_json|escapejs|default:\"{}\" }}');")
c = Context({"data_json": data_json})
print(t.render(c))
