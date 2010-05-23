#!/usr/bin/env python
"""\
Usage: %prog [options] [-r] RULES [-t] THEME

  THEME is an html file.
  RULES is a file defining a set of xdv rules in css syntax, e.g:
    <rules xmlns="http://namespaces.plone.org/xdv">
        <copy content="//div[@id='content-wrapper']"
              theme="//div[@id='page-content']"/>
    </rules>\
"""
usage = __doc__

import re
import os.path
import sys
import logging
from lxml import etree
from optparse import OptionParser

from utils import namespaces
from cssrules import convert_css_selectors

logger = logging.getLogger('xdv')

HERE = os.path.dirname(__file__)

IMPORT_STYLESHEET = re.compile(r'''(@import\s+(?:url\(['"]?|['"]))(.+)(['"]?\)|['"])''', re.IGNORECASE)

COMPILER_PATH = os.path.join(HERE, 'compiler.xsl')

UPDATE_PATH = os.path.join(HERE, 'update-namespace.xsl')
update_transform = etree.XSLT(etree.parse(UPDATE_PATH))

def update_namespace(rules):
    """Convert old namespace to new namespace in place
    """
    if rules.xpath("//*[namespace-uri()='%s']" % namespaces['old']):
        logger.warning('The %s namespace is deprecated, use %s instead.' % (namespaces['old'], namespaces['xdv']))
        return update_transform(rules)
    else:
        return rules

class CompileResolver(etree.Resolver):
    def __init__(self, rules, extra=None):
        self.rules = rules
        self.extra = extra
        
    def resolve(self, url, pubid, context):
        if url == '__xdv__rules':
            return self.resolve_string(self.rules, context)
        if url == '__xdv__extra' and self.extra is not None:
            return self.resolve_string(self.extra, context)

def to_absolute(path, prefix):
    """Make a url/path into an absolute URL by applying the given prefix
    """
    # Absolute path or full url
    if path.startswith('/') or '://' in path:
        return path
    
    absolute = "%s/%s" % (prefix, path)
    if '://' in absolute:
        return absolute
        
    normalized = os.path.normpath(absolute)
    if os.path.sep != '/':
        normalized = normalized.replace(os.path.sep, '/')
    return normalized    

def apply_absolute_prefix(theme_doc, absolute_prefix):
    if absolute_prefix.endswith('/'):
        absolute_prefix = absolute_prefix[:-1]
    for node in theme_doc.xpath('*//style | *//script | *//img | *//link | *//input | *//comment() '):
        if node.tag in ('img', 'script', 'input',):
            src = node.get('src')
            if src:
                node.set('src', to_absolute(src, absolute_prefix))
        elif node.tag == 'link':
            href = node.get('href')
            if href:
                node.set('href', to_absolute(href, absolute_prefix))
        elif node.tag == 'style' or node.tag == etree.Comment and node.text.startswith("[if IE"):
            node.text = IMPORT_STYLESHEET.sub(lambda match: match.group(1) + to_absolute(match.group(2), absolute_prefix) + match.group(3), node.text)

def compile_theme(rules, theme, extra=None, css=True, xinclude=True, absolute_prefix=None, update=True, trace=False, includemode=None, parser=None, compiler_parser=None, rules_parser=None, access_control=None):
    """Invoke the xdv compiler.
    
    * ``rules`` is the rules file
    * ``theme`` is the theme file
    * ``extra`` is an optional XSLT file with XDV extensions (depracated, use
      inline xsl in the rules instead)
    * ``css``   can be set to False to disable CSS syntax support (providing a
      moderate speed gain)
    * ``xinclude`` can be set to False to disable XInclude support during the
      compile phase (providing a moderate speed gain)
    * ``absolute_prefix`` can be set to a string that will be prefixed to any
      *relative* URL referenced in an image, link or stylesheet in the theme
      HTML file before the theme is passed to the compiler. This allows a
      theme to be written so that it can be opened and views standalone on the
      filesystem, even if at runtime its static resources are going to be
      served from some other location. For example, an
      ``<img src="images/foo.jpg" />`` can be turned into 
      ``<img src="/static/images/foo.jpg" />`` with an ``absolute_prefix`` of
      "/static".
    * ``update`` can be set to False to disable the automatic update support for
      the old Deliverance 0.2 namespace (for a moderate speed gain)
    * ``trace`` can be set to True to enable compiler trace information
    * ``includemode`` can be set to 'document', 'esi' or 'ssi' to change the
      way in which includes are processed
    * ``parser`` can be set to an lxml parser instance; the default is an HTMLParser
    * ``compiler_parser``` can be set to an lxml parser instance; the default is a
      XMLParser
    * ``rules_parser`` can be set to an lxml parser instance; the default is a
      XMLParse.
    """
    
    if rules_parser is None:
        rules_parser = etree.XMLParser(recover=False)
    rules_doc = etree.parse(rules, parser=rules_parser)
    
    if xinclude:
        rules_doc.xinclude()
    if update:
        rules_doc = update_namespace(rules_doc)
    if css:
        convert_css_selectors(rules_doc)
    
    if parser is None:
        parser = etree.HTMLParser()
    theme_doc = etree.parse(theme, parser=parser)
    
    if absolute_prefix:
        apply_absolute_prefix(theme_doc, absolute_prefix)
    
    if compiler_parser is None:
        compiler_parser = etree.XMLParser()
    if access_control is None:
        access_control = etree.XSLTAccessControl(read_file=True, write_file=False, create_dir=False, read_network=False, write_network=False)
    compiler_transform = etree.XSLT(etree.parse(COMPILER_PATH, parser=compiler_parser), access_control=access_control)

    params = dict(rulesuri="'__xdv__rules'")
    if extra:
        params['extraurl'] = "'__xdv__extra'"
        resolver = CompileResolver(etree.tostring(rules_doc), etree.tostring(etree.parse(extra)))
    else:
        resolver = CompileResolver(etree.tostring(rules_doc))
    if trace:
        params['trace'] = '1'
    if includemode:
        params['includemode'] = "'%s'" % includemode

    compiler_parser.resolvers.add(resolver)
    compiled = compiler_transform(theme_doc, **params)
    for msg in compiler_transform.error_log:
        logger.info(msg)
    return compiled

def main():
    """Called from console script
    """
    parser = OptionParser(usage=usage)
    parser.add_option("-o", "--output", metavar="output.xsl",
                      help="Output filename (instead of stdout)",
                      dest="output", default=sys.stdout)
    parser.add_option("-p", "--pretty-print", action="store_true",
                      help="Pretty print output (may alter rendering in browser)",
                      dest="pretty_print", default=False)
    parser.add_option("--trace", action="store_true",
                      help="Compiler trace logging",
                      dest="trace", default=False)
    parser.add_option("--xinclude", action="store_true",
                      help="Run XInclude on rules.xml (depracated, xinclude is always run)",
                      dest="xinclude", default=True)
    parser.add_option("-a", "--absolute-prefix", metavar="/",
                      help="relative urls in the theme file will be made into absolute links with this prefix.",
                      dest="absolute_prefix", default=None)
    parser.add_option("-i", "--includemode", metavar="INC",
                      help="include mode (document, ssi or esi)",
                      dest="includemode", default=None)
    parser.add_option("-n", "--network", action="store_true",
                      help="Allow reads to the network to fetch resources",
                      dest="read_network", default=False)
    parser.add_option("-t", "--theme", metavar="theme.html",
                      help="Theme file",
                      dest="theme", default=None)
    parser.add_option("-r", "--rules", metavar="rules.xml",
                      help="XDV rules file", 
                      dest="rules", default=None)
    parser.add_option("-e", "--extra", metavar="extra.xsl",
                      help="Extra XSL to be included in the transform (depracated, use inline xsl in the rules instead)",
                      dest="extra", default=None)
    (options, args) = parser.parse_args()

    if options.rules is None and options.theme is None:
        if len(args) == 2:
            options.rules, options.theme = args
        else:
            parser.error("Wrong number of arguments.")
    elif not(options.rules is not None and options.theme is not None):
        parser.error("Both theme and rules must be supplied as options or as arguments.")

    if options.trace:
        logger.setLevel(logging.DEBUG)

    access_control = etree.XSLTAccessControl(read_file=True, write_file=False, create_dir=False, read_network=options.read_network, write_network=False)

    output_xslt = compile_theme(rules=options.rules, theme=options.theme, extra=options.extra, trace=options.trace, xinclude=options.xinclude, absolute_prefix=options.absolute_prefix, includemode=options.includemode, access_control=access_control)
    output_xslt.write(options.output, encoding='utf-8', pretty_print=options.pretty_print)

if __name__ == '__main__':
    main()
