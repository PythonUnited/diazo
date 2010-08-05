#!/usr/bin/env python
"""\
Usage: %prog -x TRANSFORM CONTENT

  TRANSFORM is the compiled theme transform
  CONTENT is an html file.
  
Usage: %prog -r RULES [options] CONTENT
"""
usage = __doc__

import logging
import sys
import os.path

from lxml import etree

from xdv.compiler import compile_theme
from xdv.utils import AC_READ_NET, AC_READ_FILE, _createOptionParser

logger = logging.getLogger('xdv')

class RunResolver(etree.Resolver):
    def __init__(self, directory):
        self.directory = directory
        
    def resolve(self, url, id, context):
        # libxml2 does not do this correctly on it's own with the HTMLParser
        # but it does work in Apache
        if '://' in url or url.startswith('/'):
            # It seems we must explicitly resolve the url here
            return self.resolve_filename(url, context)
        url = os.path.join(self.directory, url)
        return self.resolve_filename(url, context)

def main():
    """Called from console script
    """
    op = _createOptionParser(usage=usage)
    op.add_option("-x", "--xsl", metavar="transform.xsl",
                      help="XSL transform", 
                      dest="xsl", default=None)
    (options, args) = op.parse_args()

    if len(args) > 2:
        op.error("Wrong number of arguments.")
    elif len(args) == 2:
        if options.xsl or options.rules:
            op.error("Wrong number of arguments.")
        path, content = args
        if path.lower().endswith('.xsl'):
            options.xsl = path
        else:
            options.rules = path
    elif len(args) == 1:
        content, = args
    else:
        op.error("Wrong number of arguments.")
    if options.rules is None and options.xsl is None:
        op.error("Must supply either options or rules")

    if options.trace:
        logger.setLevel(logging.DEBUG)

    parser = etree.HTMLParser()
    parser.resolvers.add(RunResolver(os.path.dirname(content)))

    if options.xsl is not None:
        output_xslt = etree.parse(options.xsl)
    else:
        output_xslt = compile_theme(
            rules=options.rules,
            theme=options.theme,
            extra=options.extra,
            parser=parser,
            read_network=options.read_network,
            absolute_prefix=options.absolute_prefix,
            includemode=options.includemode,
            )

    if content == '-':
        content = sys.stdin

    if options.read_network:
        access_control = AC_READ_NET
    else:
        access_control = AC_READ_FILE

    transform = etree.XSLT(output_xslt, access_control=access_control)
    content_doc = etree.parse(content, parser=parser)
    output_html = transform(content_doc)
    output_html.write(options.output, encoding='UTF-8', pretty_print=options.pretty_print)
    for msg in transform.error_log:
        logger.warn(msg)

if __name__ == '__main__':
    main()
