#!/usr/bin/python
# -*- coding: utf-8 -*-

import lxml.etree
import lxml.html
from lxml.html.clean import Cleaner
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
        'fix_paragraph': r'<br[^>]*>\s*<p',
        'videos': r'http:\/\/(www\.)?(youtube|vimeo|youku|tudou)\.com',
        'skip_footnote_link': r'^\s*(\[?[a-z0-9]{1,2}\]?|^|edit|citation needed)\s*$',
        'next_link': r'(next|weiter|continue|>([^\|]|$)|»([^\|]|$))',
        'pre_link': r'(prev|earl|old|new|<|«)',
        }

    def __init__(self):
        self.compile_all()
        self.content_scores = {}

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
        self.url = url
        html = self.smart_decode(html)
        cleaner = Cleaner(page_structure=False, add_nofollow=True,
                          style=True, safe_attrs_only=True)
        html = cleaner.clean_html(html)
        tree = lxml.html.fromstring(html)
        body = tree.xpath('//body')[0]
        article = self.grab_article(body)
        return cleaner.clean_html(article)

    def get_link_density(self, element):
        text_length = len(element.text_content())
        if text_length == 0:
            return 0
        link_length = 0
        for e in element.findall('.//a'):
            link_length = link_length + len(e.text_content())
        return float(link_length) / text_length

    def remove_whitespace(self, node):
        for e in node.iterdescendants():
            if e.text is not None:
                e.text = e.text.strip()
            if e.tail is not None:
                e.tail = e.tail.strip()
        if node.text is not None:
            node.text = node.text.strip()
        if node.tail is not None:
            node.tail = node.tail.strip()

    def clean_up(self, html):
        self.kill_breaks(html)
        node = lxml.html.fromstring(html)
        self.prepare_article(node)
        if self.url:
            node.make_links_absolute(self.url)
        self.remove_whitespace(node)
        html = lxml.html.tostring(node)
        html = self.regexps['fix_paragraph'].sub('<p', html)
        return html

    def clean_headers(self, node):
        for i in [1, 2, 3]:
            elements = node.findall('.//h%d' % i)
            for e in elements:
                if self.get_class_weight(e) < 0 \
                    or self.get_link_density(e) > 0.33:
                    e.drop_tree()

    def prepare_article(self, node):
        self.clean_conditionally(node, 'form')
        self.clean_tag(node, 'object')
        self.clean_tag(node, 'h1')

        h2_elements = node.findall('.//h2')
        if len(h2_elements) == 1:
            self.clean_tag(node, 'h2')
        self.clean_tag(node, 'iframe')

        self.clean_headers(node)

        self.clean_conditionally(node, 'table')
        self.clean_conditionally(node, 'ul')
        self.clean_conditionally(node, 'div')

        p_elements = node.findall('.//p')
        for e in p_elements:
            img_count = len(e.findall('.//img'))
            embed_count = len(e.findall('.//embed'))
            object_count = len(e.findall('.//object'))

            if img_count == 0 and embed_count == 0 and object_count \
                == 0 and e.text_content().strip() == '':
                try:
                    e.drop_tree()
                except:
                    pass

    def get_comma_count(self, node):
        text = node.text_content()
        eng = len(text.split(','))
        chi = len(text.split(u'，'))
        return eng + chi

    def kill_breaks(self, html):
        return self.regexps['kill_breaks'].sub('<br />', html)

    def clean_tag(self, node, tag):
        elements = node.findall('.//' + tag)
        for e in elements:
            if tag.lower() in ['object', 'embed']:
                attributes = e.values().join('|')
                if self.regexps['videos'].search(attributes):
                    continue
                if self.regexps['videos'].search(lxml.html.tostring(e)):
                    continue
            try:
                e.drop_tree()
            except:
                pass

    def clean_conditionally(self, node, tag):
        elements = node.findall('.//' + tag)

        for e in elements:
            weight = self.get_class_weight(e)
            content_score = self.get_content_score(e)
            if weight + content_score < 0:
                e.drop_tree()
            elif self.get_comma_count(e) < 10:
                p = len(e.findall('.//p'))
                img = len(e.findall('.//img'))
                li = len(e.findall('.//li'))
                input = len(e.findall('.//input'))

                embed_count = 0
                for ele in e.findall('.//embed'):
                    src = ele.get('src')
                    if src and not self.regexps['video'].search(src):
                        embed_count = embed_count + 1

                link_density = self.get_link_density(e)
                content_length = len(e.text_content())
                to_remove = False

                if img > p and img > 1:  # div wrapper for img should not be remove
                    to_remove = True
                elif li > p and not e.tag.lower() in ['ul', 'ol']:
                    to_remove = True
                elif input > p / 3:
                    to_remove = True
                elif content_length < 25 and (img == 0 or img > 3):
                    to_remove = True
                elif weight < 25 and link_density > 0.2:
                    to_remove = True
                elif weight >= 25 and link_density > 0.5:
                    to_remove = True
                elif embed_count == 1 and content_length < 75 \
                    or embed_count > 1:
                    to_remove = True

                if to_remove:
                    e.drop_tree()

    def get_content_score(self, node):
        if self.content_scores.get('node'):
            return self.content_scores['node']
        return 0

    def init_score(self, node):
        tag = node.tag.lower()
        if tag in ['div']:
            score = 5
        elif tag in ['pre', 'td', 'blockquote']:
            score = 3
        elif tag in [
            'address',
            'ol',
            'ul',
            'dl',
            'dd',
            'dt',
            'li',
            'form',
            ]:
            score = -3
        elif tag in [
            'h1',
            'h2',
            'h3',
            'h4',
            'h5',
            'h6',
            'th',
            ]:
            score = -5
        else:
            score = 0
        return score + self.get_class_weight(node)

    def get_class_weight(self, node):
        weight = 0
        class_name = node.get('class')
        if class_name and len(class_name) > 0:
            if self.regexps['negative'].search(class_name):
                weight = weight - 25
            if self.regexps['positive'].search(class_name):
                weight = weight + 25

        id_name = node.get('id')
        if id_name and len(id_name) > 0:
            if self.regexps['negative'].search(id_name):
                weight = weight - 25
            if self.regexps['positive'].search(id_name):
                weight = weight + 25

        return weight

    def grab_article(self, tree):
        nodes_to_score = []

        need_remove = []
        for e in tree.getiterator('*'):
            name = '%s%s' % (e.get('id'), e.get('class'))
            if self.regexps['unlikely'].search(name) \
                and self.regexps['maybe'].search(name) is None:
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
                else:
                    text = e.text
                    if text and len(text.strip()) > 4:
                        p_element = lxml.html.fromstring('<p>'
                                + text.strip() + '</p>')
                        e.text = ''
                        e.insert(0, p_element)
                        nodes_to_score.append(p_element)
                    for child_e in e.getchildren():
                        text = child_e.tail
                        if text and len(text.strip()) > 4:
                            if child_e.tag.lower() in [
                                'b',
                                'i',
                                'strong',
                                'em',
                                'a',
                                'span',
                                'del',
                                'img',
                                ]:
                                pre_e = child_e.getprevious()
                                child_e.tail = text.strip()
                                if pre_e is not None \
                                    and pre_e.tag.lower() == 'p':
                                    pre_e.append(child_e)
                                    nodes_to_score.append(pre_e)
                                else:
                                    p_element = \
    lxml.html.fromstring('<p/>')
                                    child_e.addnext(p_element)
                                    child_e.drop_tree()
                                    p_element.insert(0, child_e)
                            else:
                                p_element = lxml.html.fromstring('<p>'
                                        + text.strip() + '</p>')
                                child_e.tail = ''
                                child_e.addnext(p_element)
                                nodes_to_score.append(p_element)
        scores = {}
        for e in nodes_to_score:
            parent_node = e.getparent()
            if parent_node is None:
                continue

            grand_parent_node = parent_node.getparent()
            text = e.text_content()
            if text is None or len(text) < 25:
                continue

            if not parent_node in scores:
                scores[parent_node] = self.init_score(parent_node)

            if grand_parent_node is not None and not grand_parent_node \
                in scores:
                scores[grand_parent_node] = \
                    self.init_score(grand_parent_node)

            score = 1
            score = score + len(text.split(u'，'))  # Chinese comma
            score = score + len(text.split(','))
            score = score + min(3, len(text) / 100)

            scores[parent_node] = scores[parent_node] + score
            if grand_parent_node is not None:
                scores[grand_parent_node] = scores[grand_parent_node] \
                    + score * 0.5

        max_score = -1
        candidate = None
        for e in scores.keys():
            score = scores[e]
            score = score * (1 - self.get_link_density(e))
            scores[e] = score
            if score > max_score:
                max_score = score
                candidate = e

        self.content_scores = scores

        if candidate is None:
            candidate = tree  # fallback to body
            scores[candidate] = self.init_score(candidate)

        sibling_score_threshold = max(10, scores[candidate] * 0.2)

        article_node = lxml.html.fromstring('<div/>')
        for e in candidate.getparent().iterchildren('*'):
            append = False

            if e == candidate:
                append = True

            bonus = 0
            class_name = e.get('class')
            candidate_class_name = candidate.get('class')
            if candidate_class_name and class_name and class_name \
                == candidate_class_name:
                bonus = 0.2 * scores[candidate]
            if e in scores and scores[e] + bonus \
                > sibling_score_threshold:
                append = True
            if e.tag.lower() == 'p':
                link_density = self.get_link_density(e)
                text_length = len(e.text_content())
                if text_length > 80 and link_density < 0.25:
                    append = True
                elif link_density == 0:
                    append = True

            if append:
                if e.tag.lower() not in ['p', 'div']:
                    e.tag = 'div'
                article_node.append(e)

        html = lxml.html.tostring(article_node)
        return self.clean_up(html)


def main():
    import sys
    hitomi = Hitomi()
    if len(sys.argv) < 2:
        return
    with open(sys.argv[1], 'r') as f:
        print hitomi.readable(f.read())


if __name__ == '__main__':
    main()
