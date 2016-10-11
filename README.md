# Untemplate - a python untemplating engine

Popular templating engines take a text template, which is literal output text interpersed with variables, control statements, etc, and produce a literal text output. For example, the canonical `format_template` functions works as follows:

```python
template = "The {speed} {color} {animal} jumps over the lazy dog."
substitutions = {"speed": "quick", "color": "brown", "animal": "fox"}

formatted_text = format_template(template, substitutions)
```

and then `formatted_text == "The quick brown fox jumps over the lazy dog"`.

Untemplate reverses this process. Given a literal text, and a template specification, untemplate will extract the variables into a json-like structure. For example:

```python
template = "The {speed|word} {color|word} {animal|word} jumps over the lazy dog."
formatted_text = "The quick brown fox jumps over the lazy dog"

variables = untemplate(template, formatted_text)
```

and then `variables == {"speed": "quick", "color": "brown", "animal": "fox"}`

Untemplate is extremely basic. Templates support a small number of types (float, integer, word, string - everything to end of line, optstring - optional everything to end of line, ws - whitespace) and a very small set of control-like statements (beginarray, endarray, include). Templates are compiled to a single giant regular expression, so expressivity is limited by that. This also makes it quite hard to debug templates.

Despite this simplicity, for a reasonable set of "text scraping" problems, untemplate can get the job done.