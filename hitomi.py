# -*- coding: utf-8 -*-
import lxml.etree
import lxml.html
from lxml.html.clean import clean_html
import re

class Hitomi(object):

    regexps = {
        'unlikely': r'combx|comment|community|disqus|extra|foot|header|menu|remark|rss|shoutbox|sidebar|sponsor|ad-break|agegate|pagination|pager|popup|tweet|twitter|googlead',
        'maybe': r'and|article|body|column|main|shadow',
        'positive': r'article|body|content|entry|hentry|main|page|pagination|post|text|blog|story',
        'negative': r'combx|comment|com-|contact|foot|footer|footnote|masthead|media|meta|outbrain|promo|related|scroll|shoutbox|sidebar|sponsor|shopping|tags|tool|widget',
        'extraneous': r'print|archive|comment|discuss|e[\-]?mail|share|reply|all|login|sign|single',
        'div_to_p': r'<(a|blockquote|dl|div|img|ol|p|pre|table|ul)',
        'replace_brs': r'(<br[^>]*>[ \n\r\t]*){2,}',
        'replace_fonts': r'<(\/?)font[^>]*>',
        'trim': r'^\s+|\s+$',
        'normalize': r'\s{2,}',
        'kill_breaks': r'(<br\s*\/?>(\s|&nbsp;?)*){1,}',
        'videos': r'http:\/\/(www\.)?(youtube|vimeo|youku|tudou)\.com',
        'skip_footnote_link': r'^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$',
        'next_link': r'(next|weiter|continue|>([^\|]|$)|»([^\|]|$))',
        'pre_link': r'(prev|earl|old|new|<|«)',
    }

    def __init__(self):
        self.compile_all()

    def compile_all(self):
        self.regexps = {}
        for k in Hitomi.regexps:
            pattern = Hitomi.regexps[k]
            self.regexps[k] = re.compile(pattern, re.I | re.U)

    def smart_decode(self, html):
        """
        Obviously this function is not smart at all.
        Anyway, it works on most sites in Chinese.
        """
        encodings = ['utf-8', 'gbk', 'big5']
        for enc in encodings:
            try:
                return html.decode(enc)
            except:
                continue
        return html

    def readable(self, html, url=None):
        html = self.smart_decode(html)
        html = clean_html(html)
        tree = lxml.html.fromstring(html)
        body = tree.xpath('//body')[0]

        article = self.grab_article(body)
        return clean_html(article)

    def get_link_density(self, element):
        text_length = len(element.text_content())
        link_length = 0
        for e in element.findall('.//a'):
            link_length = link_length + len(e.text_content())
        return float(link_length) / text_length

    def _clean_up(self, html):
        need_drop = []
        node = lxml.html.fromstring(html)

        for e in node.getiterator():
            if e.get('class') is not None:
                    del e.attrib['class']
            if e.get('id') is not None:
                    del e.attrib['id']
            if e.tag.lower() in ['p', 'div']:
                text = e.text_content()
                if len(text.strip()) < 3:
                    need_drop.append(e)
            if e.tag.lower() == 'a' and not e.get('href'):
                need_drop.append(e)
        for e in need_drop:
            if e.getparent() is not None:
                e.drop_tree()
        self.make_paragraph(node)
        return lxml.html.tostring(node)

    def clean_up(self, html):
        while True:
            more = self._clean_up(html)
            if len(more) == len(html):
                return html
            html = more

    def make_paragraph(self, element):
        tail_text = {}
        for e in element.getiterator():
            if e.tag.lower() not in ['div', 'p']:
                continue
            if e.tail is not None:
                if len(e.tail.strip()) > 0:
                    tail_text[e] = e.tail.strip()
                    e.tail = ''
                else:
                    e.tail = e.tail.strip()
            if e.text is not None:
                e.text = e.text.strip()
        for e in tail_text.keys():
            text = tail_text[e]
            for line in text.split('\n'):
                line = line.strip()
                if len(line) == 0:
                    continue
                p_node = lxml.html.fromstring('<p>%s</p>' % line)
                e.addnext(p_node)

    def grab_article(self, tree):
        nodes_to_score = []

        need_remove = []
        for e in tree.getiterator('*'):
            name = '%s%s' % (e.get('id'), e.get('class'))
            if self.regexps['unlikely'].search(name) and self.regexps['maybe'].search(name) is None:
                need_remove.append(e)
        for e in need_remove:
            e.getparent().remove(e)

        for e in tree.getiterator('*'):
            if str(e.tag).lower() in ['p', 'td', 'pre']:
                nodes_to_score.append(e)

            if str(e.tag).lower() == 'div':
                html = lxml.etree.tostring(e)
                if self.regexps['div_to_p'].search(html) is None:
                    e.tag = 'p'
                    nodes_to_score.append(e)

        scores = {}
        for e in nodes_to_score:
            parent_node = e.getparent()
            if parent_node is None:
                continue

            grand_parent_node = parent_node.getparent()
            text = e.text_content()
            if text is None or len(text) < 25:
                continue


            if not scores.has_key(parent_node):
                scores[parent_node] = 0

            if grand_parent_node is not None and not scores.has_key(grand_parent_node):
                scores[grand_parent_node] = 0

            score = 1
            score = len(text.split(u'，')) # Chinese comma
            score = len(text.split(','))
            score = min(3, len(text) / 100)

            scores[parent_node] = scores[parent_node] + score
            if grand_parent_node is not None:
                scores[grand_parent_node] = scores[grand_parent_node] + score * 0.5
        
        max_score = -1
        candidate = None
        for e in scores.keys():
            score = scores[e]
            score = score * (1 - self.get_link_density(e))
            scores[e] = score
            if score > max_score:
                max_score = score
                candidate = e
        print scores
        # fallback to body
        if candidate is None:
            candidate = tree
            scores[candidate] = 0

        sibling_score_threshold = max(10, scores[candidate] * 0.2)

        article_node  = lxml.html.fromstring('<div/>')

        for e in candidate.getparent().iterchildren('*'):
            append = False

            if e == candidate:
                append = True

            bonus = 0
            class_name = e.get('class')
            candidate_class_name = candidate.get('class')
            if candidate_class_name and class_name and class_name == candidate_class_name:
                bonus = 0.2 * scores[candidate]
            if scores.has_key(e) and scores[e] + bonus > sibling_score_threshold:
                append = True
            if str(e.tag).lower() == 'p':
                link_density = self.get_link_density(e)
                text_length = len(e.text_content())
                if text_length > 80 and link_density < 0.25:
                    append = True
                elif link_density == 0:
                    append = True

            if append:
                if str(e.tag).lower() not in ['p', 'div']:
                    e.tag = 'div'
                article_node.append(e)

        html = lxml.html.tostring(article_node)
        return self.clean_up(html)

if __name__ == '__main__':
    hitomi = Hitomi()
    with open('example.html', 'r') as f:
        print hitomi.readable(f.read())
