  #!/usr/bin/python
import string
import re
import json
import sys
import os

# A set of type definitions: first element is regex to match, second is type converter
TYPES = {
    #'float': (r'(?:\-)?[0-9]*(?:\.[0-9]*)?(?:[eE][\-\+]?[0-9]+)?|[0-9]+', float),
    'float': (r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?|[-+]?NaN|[-+]?Infinity|[-+]?Inf', float),
    'integer': (r'[0-9]+', int),
    'word': (r'[^\s]+', str),
    'string': (r'[^\n]+', lambda s: s.strip()),
    'optstring': (r'[^\n]*', lambda s: s.strip()),
    'ws': (r'\s+', str)
}

# Single characters that should be collapsed from literal to regex. If 2 or more of one of these characters
# is seen in the literal input, it will be replaced with a regex that matches 1 or more. So for example:
#     "******* Heading *******" -> "\*+ Heading \*+"
# This adds some basic robustness to layout variations.
COLLAPSE = {
    '-',
    '*',
    ' ',
    '\n'
}

# Converts a 2D table represented as a lod (list of dicts) to a dol (dict of lists). For example:
#     [{x: 1, y: 2}, {x: 3, y: 6}] -> {x: [1, 3], y: [2, 6]}
def lod2dol(lod):
    dols = dict()
    for d in lod:
        for k in d:
            if k not in dols:
                dols[k] = []
        
    for d in lod:
        for k in dols:
            dols[k].append(d[k] if k in d else None)
            
    return dols
    
# Normalises a flat(ish) pyjson structure where hierarchy is embedded in keys using periods. For example:
#     {a.b.c: 3, a.b.d: 4, a.e: 5} -> {a: {b: {c: 3, d: 4}, e: 5}}
# Doesn't handle this case - considered improper
#     {a.b : 1, a: 2} -> {a: {b: 1, _default: 2}} - or something like this
def normalise_pyjson(d):
    dnext = dict()
    for k, v in d.items():
        if '.' in k:
            kparts = k.split('.')
            head = kparts[0]
            tail = kparts[1:]
            if head not in dnext:
                dnext[head] = dict()
            #print("!!",dnext['beta'] if 'beta' in dnext else None,head,tail,v)
            dnext[head]['.'.join(tail)] = v
        else:
            dnext[k] = v
    dout = dict()
    for k, v in dnext.items():
        if isinstance(v, dict):
            v = normalise_pyjson(v)
        dout[k] = v
    return dout
                          
# Takes a literal string and (i) collapses strings of length >= 2 of COLLAPSE chars
# into a regex that detects 1 or more and (ii) escapes everything else for regex
def escape_collapse(pre):
    out = ""
    count = 0
    curr_collapse_char = None
    for char in pre:
        if char == curr_collapse_char:
            count += 1
        else:
            if count > 1:
                out += re.escape(curr_collapse_char) + "+"
            if count == 1:
                out += re.escape(curr_collapse_char)

            if char in COLLAPSE:
                curr_collapse_char = char
                count = 1
            else:
                curr_collapse_char = None
                count = 0           
                out += re.escape(char)

    if count > 1:
        out += re.escape(curr_collapse_char) + "+"
    if count == 1:
        out += re.escape(curr_collapse_char)

    return out
    
# Exception raised if a text does not parse according to the template given
class ParseError(ValueError):
    pass
    
# A node (also the root object) in a kind of template parse tree.
class Varspec(object):
    def __init__(self, parent, pre, varname, vartype):
        self.parent = parent        # reference to parent node
        self.pre = pre or ''        # the text that comes immediately before this variable node
        self.varname = varname      # the name of this variable
        self.vartype = vartype      # the expected type of this variable
        self.children = []          # children of this node
        
    # Generate and return the regex for this template
    def gen_regex(self):
        regex = escape_collapse(self.pre)
        #print("LINE", regex)
        if self.vartype == 'root':
            for c in self.children:
                regex += c.gen_regex()
        elif self.vartype == 'array':
            regex += "((?:"
            for c in self.children:
                regex += c.gen_regex()
            regex += ")+)"
        elif self.vartype == 'beginor':
            regex += "(?:(?:"
        elif self.vartype == 'or':
            regex += ")|(?:"
        elif self.vartype == 'endor':
            regex += "))"
        elif self.vartype:
            regex += "(" + TYPES[self.vartype][0] + ")"
        return regex
        
    # Fills the given dictionary with variables extracted in groups, the result
    # of applying regex to a matching text.
    def build(self, parent_dict, groups):
        #print(self.varname, self.vartype, groups[0] if len(groups) > 0 else 'nil')
        obj = None
        if self.vartype == 'root':
            for c in self.children:
                c.build(parent_dict, groups)
        elif self.vartype == 'array':
            obj = list()
            g_children = groups.pop(0)
            groups[:] = groups[len(self.children)-1:] # swallow the child captures
            if g_children is None: # if inside a not-activated or block
                return
            regex = ""
            for c in self.children:
                regex += c.gen_regex()

            m = re.match(regex, g_children)
            while g_children and m:
                d = dict()
                c_groups = list(m.groups())
                g_children = g_children[len(m.group()):]
                for c in self.children:
                    c.build(d, c_groups)
                obj.append(d)
                m = re.match(regex, g_children)
                
            if self.varname:
                parent_dict[self.varname] = obj
            else: # flatten arrays
                dol = lod2dol(obj)
                parent_dict.update(dol)
        elif self.vartype in ('beginor', 'or', 'endor'):
                pass
        elif self.vartype:
            #print(self.vartype, groups)
            group = groups.pop(0)
            if self.varname and group is not None:  # if inside a not-activated or block
                try:
                    obj = TYPES[self.vartype][1](group)
                    parent_dict[self.varname] = obj
                except ValueError as e:
                    print(group)
                    raise e    
   
def build_parser(template_filename, prefix=''):
    working_template_path, _ = os.path.split(template_filename)
    with open(template_filename) as f:
        template = f.read()

    insertions = string.Formatter().parse(template)

    parent = Varspec(None,None,None,'root')
    for pre, spec, _, _ in insertions:
        if spec:
            varname, vartype = spec.split('|')
            if prefix:
                if varname:
                    varname = prefix + "." + varname
            if vartype == 'beginarray':
                child = Varspec(parent, pre, varname, 'array')
                parent.children.append(child)
                parent = child
            elif vartype == 'endarray':
                child = Varspec(parent, pre, None, None)
                parent.children.append(child)
                parent = parent.parent

#           elif vartype == 'beginor':
#               child = Varspec(parent, pre, None, 'optionset')
#               grandchild = Varspec(child, None, varname, 'option')
#               parent.children.append(child)
#               child.children.append(grandchild)
#               parent = grandchild
#           elif vartype == 'or':
#               parent = parent.parent
#               grandchild = Varspec(parent, pre, None, None)
#               parent.children.append(child)
#               parent.parent.children.append(next_option_child)
#               next_option_child =
#           elif vartype == 'endor':
#               child = Varspec(parent, pre, None, None)
#               parent.children.append(child)
#               parent = parent.parent.parent

            elif vartype.startswith('include '):
                _, include_file = vartype.split()
                include_file = os.path.join(working_template_path, include_file)
                if prefix:
                    newprefix = prefix + "." + varname
                else:
                    newprefix = varname
                subtree = build_parser(include_file, newprefix)
                subtree.pre = pre 
                parent.children.append(subtree)
            else:
                child = Varspec(parent, pre, varname, vartype)
                parent.children.append(child)
        else:
            child = Varspec(parent, pre, None, None)
            parent.children.append(child)
            
    return parent
    
def parse_text(parser, text):      
    regex = parser.gen_regex()
    with open("debug.regex", "w") as fout:
        fout.write(regex)
        
    m = re.match(regex, text)
    #print(len(m.groups()), m.groups())
    if m:
        obj = dict()
        parser.build(obj, list(m.groups()))
        obj = normalise_pyjson(obj)
        return obj
    else:
        raise ParseError()

# Given a template_filename (or list of possible templates) and a text_filename, applies the template to
# the text and return the pyjson structure of variables extracted. Raises ParseError if no template
# matched.
def untemplate(template_filename, text_filename):
    with open(text_filename) as f:
        text = f.read()
    
    return untemplate_string(template_filename, text)

def untemplate_string(template_filename, text):
    if isinstance(template_filename, str):
        template_filename = [template_filename]
        
    for tfn in template_filename:
        parser = build_parser(tfn)
        try:
            obj = parse_text(parser, text)
            return obj
        except ParseError:
            pass
            
    raise ParseError()
          
if __name__ == "__main__":
    text_filename = sys.argv[1]
    template_filename = sys.argv[2:]

    obj = untemplate(template_filename, text_filename)

    print(json.dumps(obj, indent=4))
