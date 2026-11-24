"""Typeset paper.tex and split its aside sections into standalone Sage pages."""
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
import json
import posixpath
import re
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
HOME = '.'
MARK = '<svg class="folio-mark" viewBox="0 0 36 36" aria-hidden="true"><path d="m3 12 15-8.5L33 12l-15 8.5zM3 18l15 8.5L33 18M3 24l15 8.5L33 24"/></svg>'
CHEVRON = '<svg class="chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg>'
ENVIRONMENTS = {'theorem', 'lemma', 'corollary', 'proposition', 'definition', 'example', 'bdhrestatement'}
# The backlink lands on the part of the main proof that uses the aside.
RETURN_TO = {'sharp-p': 'thm:eth', 'permanent': 'thm:bdh',
             'polynomial-interpolation': 'cor:recover', 'hadamard-matrix': 'lem:hadamard'}


def text_node(value):
    return {'t': 'Str', 'c': value}


def raw_block(markup):
    return {'t': 'RawBlock', 'c': ['html', markup]}


def text_of(inlines):
    return ''.join(token.get('c', '') if token['t'] == 'Str' else ' '
                   for token in inlines).strip()


def link_to(current, page, anchor=''):
    if current == page and anchor:
        return '#' + anchor
    return posixpath.relpath(page, current) + '/' + ('#' + anchor if anchor else '')


def pandoc(source, reader, writer, *options):
    return subprocess.run(
        ['pandoc', '-f', reader, '-t', writer, *options],
        input=source, text=True, stdout=subprocess.PIPE, check=True,
    ).stdout


@dataclass
class Section:
    anchor: str
    title: str
    page: str
    page_number: int
    guide: bool = False
    blocks: list = field(default_factory=list)
    subsections: list = field(default_factory=list)


def group_sections(document):
    sections = []
    page_numbers = {HOME: 1}
    for block in document['blocks']:
        if block['t'] == 'Header' and block['c'][0] == 1:
            _, (anchor, classes, _), text = block['c']
            title = text_of(text)
            guide = 'unnumbered' in classes
            aside = re.match(r'^aside\b[\s:]*', title, flags=re.IGNORECASE)
            page = HOME
            if aside:
                title = title[aside.end():].strip()
                title = title[:1].upper() + title[1:]
                slug_source = anchor[4:] if anchor.startswith('sec:') else title
                slug = re.sub('[^a-z0-9]+', '-', slug_source.lower().replace('#', 'sharp-')).strip('-')
                page = 'asides/' + slug
            elif anchor == 'eth-false':
                title = 'Theorems and plan'
            elif anchor == 'proof':
                title = 'Proof'
            page_number = page_numbers.setdefault(page, len(page_numbers) + 1)
            sections.append(Section(anchor, title, page, page_number, guide))
        else:
            sections[-1].blocks.append(block)
    return sections


def headed_statement(block, number, level):
    """Turn Pandoc's run-in theorem title into a navigable heading."""
    body = block['c'][1]
    tokens = body[0]['c']
    label = tokens[0]['c']
    label[-1] = text_node(number)
    title_tokens = tokens[1:]
    while title_tokens and title_tokens[0]['t'] in ('Space', 'SoftBreak'):
        title_tokens.pop(0)
    name, rest = [], title_tokens
    if title_tokens and title_tokens[0]['t'] == 'Str' and title_tokens[0]['c'].startswith('('):
        end = next((i for i, token in enumerate(title_tokens)
                    if token['t'] == 'Str' and token['c'].endswith(').')), None)
        if end is not None:
            name, rest = title_tokens[:end + 1], title_tokens[end + 1:]
            name[0]['c'] = name[0]['c'][1:]
            name[-1]['c'] = name[-1]['c'][:-2]
            name = [token for token in name if token.get('c') != '']
    heading = [{'t': 'Span', 'c': [['', ['result-number'], []], label]}]
    if name:
        heading += [{'t': 'Space'}] + name
    body[:1] = [{'t': 'Header', 'c': [level, ['', ['result-title'], []], heading]},
                {'t': 'Para', 'c': rest}]


def index_statements(sections):
    targets, numbers = {}, {}
    counts = Counter()
    for section in sections:
        targets[section.anchor] = section.page
        level = 3 if section.page == HOME else 2
        for block in section.blocks:
            if block['t'] == 'Header' and section.page == HOME:
                # The main reader wraps each manuscript section in an h2.
                block['c'][0] += 1
                depth, (anchor, _, _), title = block['c']
                level = depth + 1
                if depth == 3:
                    section.subsections.append((anchor, text_of(title)))
            if block['t'] in ('Figure', 'Header'):
                attrs = block['c'][1] if block['t'] == 'Header' else block['c'][0]
                if attrs[0]:
                    targets[attrs[0]] = section.page
            if block['t'] != 'Div':
                continue
            (anchor, classes, _), _ = block['c']
            if anchor:
                targets[anchor] = section.page
            if ENVIRONMENTS.intersection(classes):
                counts[section.page] += 1
                number = f'{section.page_number}.{counts[section.page]}'
                if anchor:
                    numbers[anchor] = number
                headed_statement(block, number, level)
    return targets, numbers


MATH_LINK = re.compile(r'\\hyperref\[([^\]]+)\]\{([^{}]+)\}')


def rewrite(node, current, targets, numbers):
    """Resolve references across pages before Pandoc typesets the mathematics."""
    if isinstance(node, list):
        return [rewrite(item, current, targets, numbers) for item in node]
    if not isinstance(node, dict):
        return node
    kind = node.get('t')
    if kind == 'Math':
        form, tex = node['c']
        if tex.lstrip().startswith(r'\displaystyle'):
            form = {'t': 'DisplayMath'}
        match = MATH_LINK.search(tex)
        if match:
            anchor, label = match.groups()
            math = {'t': 'Math', 'c': [form, MATH_LINK.sub(lambda m: m.group(2), tex)]}
            attrs = ['', ['formula-reference'], [['aria-label', label + ' lemma']]]
            return {'t': 'Link', 'c': [attrs, [math], [link_to(current, targets[anchor], anchor), '']]}
        return {'t': 'Math', 'c': [form, tex]}
    if kind == 'Image':
        attrs, label, (url, title) = node['c']
        if url.startswith('assets/'):
            url = posixpath.relpath(url, current)
        return {'t': 'Image', 'c': [attrs, label, [url, title]]}
    if kind == 'Link':
        attrs, label, (url, title) = node['c']
        reference = dict(attrs[2]).get('reference')
        if reference in numbers:
            label = [text_node(numbers[reference])]
        if url.startswith('#') and url[1:] in targets:
            anchor = url[1:]
            url = link_to(current, targets[anchor], anchor)
        elif urlsplit(url).netloc:
            attributes = dict(attrs[2])
            attributes['target'] = '_blank'
            relations = set(attributes.get('rel', '').split())
            attributes['rel'] = ' '.join(sorted(relations | {'noopener'}))
            attrs = [attrs[0], attrs[1], list(attributes.items())]
        return {'t': 'Link', 'c': [attrs, rewrite(label, current, targets, numbers), [url, title]]}
    return {key: rewrite(value, current, targets, numbers) for key, value in node.items()}


def display_math(token):
    if token['t'] != 'Math':
        return False
    form, tex = token['c']
    return form['t'] == 'DisplayMath' or tex.lstrip().startswith(r'\displaystyle')


def display_block(token):
    # A top-level comma and \qquad separate independent mathematical expressions.
    # Keep each expression intact, and let the page wrap between them if needed.
    tex = token['c'][1]
    cuts = []
    for gap in re.finditer(r'(?<=,)\s*\\qquad\s*', tex):
        prefix = tex[:gap.start()]
        if (prefix.count('{') == prefix.count('}') and
                prefix.count(r'\begin{') == prefix.count(r'\end{')):
            cuts.append(gap)
    start = 0
    parts = []
    for gap in cuts:
        parts.append(tex[start:gap.start()])
        start = gap.end()
    parts.append(tex[start:])
    boxes = []
    for part in parts:
        math = {'t': 'Math', 'c': [{'t': 'DisplayMath'}, part]}
        boxes.append({'t': 'Div', 'c': [['', ['math-scroll'], []], [{'t': 'Plain', 'c': [math]}]]})
    if len(boxes) == 1:
        return boxes[0]
    return {'t': 'Div', 'c': [['', ['equation-sequence'], []], boxes]}


def equation_blocks(blocks):
    """Give wide display equations their own locally scrollable container."""
    result = []
    for block in blocks:
        if block['t'] == 'Div':
            block['c'][1] = equation_blocks(block['c'][1])
        if block['t'] != 'Para':
            result.append(block)
            continue
        prose = []
        for token in block['c']:
            if not display_math(token):
                prose.append(token)
                continue
            if any(t['t'] not in ('Space', 'SoftBreak') for t in prose):
                result.append({'t': 'Para', 'c': prose})
            result.append(display_block(token))
            prose = []
        if any(t['t'] not in ('Space', 'SoftBreak') for t in prose):
            result.append({'t': 'Para', 'c': prose})
    return result


def outline(current, sections):
    def item(label, page, anchor='', number=None):
        state = ' aria-current="page"' if page == current and not anchor else ''
        tracking = f' data-section="{escape(anchor)}"' if page == current and anchor else ''
        prefix = f'<span>{number}.</span> ' if number is not None else ''
        return f'<a href="{link_to(current, page, anchor)}"{state}{tracking}>{prefix}{escape(label)}</a>'

    main_links = []
    for section in sections:
        if section.page != HOME or section.guide:
            continue
        children = ''.join(f'<li>{item(title, HOME, anchor)}</li>' for anchor, title in section.subsections)
        sublist = f'<ul class="on-page">{children}</ul>' if children else ''
        main_links.append(f'<li>{item(section.title, HOME, section.anchor)}{sublist}</li>')
    aside_links = ''.join(f'<li>{item(section.title, section.page, number=section.page_number)}</li>'
                          for section in sections if section.page != HOME)
    return (f'<ul class="paper-outline"><li>{item("Main proof", HOME, number=1)}'
            f'<ul class="on-page">{"".join(main_links)}</ul></li></ul>'
            f'<p class="outline-label">Asides</p><ul class="paper-outline">{aside_links}</ul>')


def write_reader(dist, current, title, paper, author, nav, content, heading_id, return_anchor, stylesheets):
    base = link_to(current, HOME)
    home = escape(base)
    stylesheet_links = '\n'.join(f'<link rel="stylesheet" href="{home}{url}">' for url in stylesheets)
    if current == HOME:
        byline = f'Main proof <span aria-hidden="true">·</span> {escape(author)}' if author else 'Main proof'
        footer = f'<a href="{home}downloads/eth-false.tex" download>LaTeX source</a>'
    else:
        byline = 'Aside'
        footer = f'<a href="{link_to(current, HOME, return_anchor)}">Return to the main proof</a>'
    page = f'''<!doctype html>
<html lang="en" data-layout="sage"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · {escape(paper) if current != HOME else 'Main proof'}</title>
<link rel="icon" href="{home}assets/folio.svg" type="image/svg+xml">
{stylesheet_links}
<script type="module" src="{home}paper.mjs"></script></head>
<body class="paper-reader"><a class="skip" href="#main">Skip to text</a>
<header class="masthead"><a class="paper-name" href="{home}">{MARK}<span>{escape(paper)}</span></a>
<div class="header-menus"><details class="menu contents-menu"><summary>Contents {CHEVRON}</summary>
<nav class="menu-panel" aria-label="Paper contents">{nav}</nav></details></div></header>
<div class="reader-shell"><aside class="rail"><nav aria-label="Paper contents"><h2>Contents</h2>{nav}</nav></aside>
<main id="main"><article class="chapter"><header class="chapter-heading">
<p>{byline}</p><h1 id="{escape(heading_id)}">{escape(title)}</h1></header>
{content}<footer class="paper-footer">{footer}</footer></article></main></div></body></html>
'''
    output = dist / current / 'index.html'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding='utf-8')


def build(dist):
    tex = (SOURCE / 'paper.tex').read_text(encoding='utf-8')
    # Each lecture panel carries its web export, description, and printable TikZ drawing.
    web_tex = tex.replace(r'\begin{document}', (
        r'\renewcommand{\lecturedrawing}[3]{\includegraphics[alt={#2}]{assets/figures/#1.png}}'
        '\n' + r'\begin{document}'
    ), 1)
    document = json.loads(pandoc(web_tex, 'latex', 'json'))
    sections = group_sections(document)
    targets, numbers = index_statements(sections)
    paper = text_of(document['meta']['title']['c'])
    authors = document['meta'].get('author', {}).get('c', [])
    author = ', '.join(text_of(person['c']) for person in authors)
    side_sections = [section for section in sections if section.page != HOME]
    asides = {section.page: section for section in side_sections}
    if len(asides) != len(side_sections):
        raise ValueError('Give each aside a distinct section title.')
    pages = [HOME, *asides]
    stylesheets = []
    for name in ('styles.css', 'paper.css'):
        source = dist / name
        version = sha256(source.read_bytes()).hexdigest()[:12]
        stylesheets.append(f'{name}?v={version}')

    for page in pages:
        blocks = []
        for section in (s for s in sections if s.page == page):
            body = equation_blocks(section.blocks)
            if page != HOME:
                # An empty "Proof:" line in the draft follows the restatement.
                for i, block in enumerate(body):
                    if block['t'] == 'Para' and text_of(block['c']) == 'Proof:' and i == len(body) - 1:
                        bdh_url = next((url for url in external_links(document['blocks'])
                                        if url.endswith('/01perm.pdf')), None)
                        if bdh_url:
                            proof_link = {'t': 'Link', 'c': [
                                ['', [], []], [text_node('Proof in the original paper')], [bdh_url, '']]}
                            body[i] = {'t': 'Div', 'c': [
                                ['', ['original-proof'], []], [{'t': 'Para', 'c': [proof_link]}]]}
                blocks.extend(body)
            else:
                anchor, label = escape(section.anchor), escape(section.title)
                if section.guide:
                    blocks += [raw_block(f'<details class="reading-guide" id="{anchor}"><summary>{label}</summary>'),
                               *body, raw_block('</details>')]
                else:
                    blocks += [raw_block(f'<section class="proof-section" aria-labelledby="{anchor}"><h2 id="{anchor}">{label}</h2>'),
                               *body, raw_block('</section>')]
        fragment = {'pandoc-api-version': document['pandoc-api-version'], 'meta': {},
                    'blocks': rewrite(blocks, page, targets, numbers)}
        content = pandoc(json.dumps(fragment), 'json', 'html5', '--mathml', '--wrap=none', '--fail-if-warnings')
        title = asides[page].title if page in asides else paper
        heading_id = asides[page].anchor if page in asides else 'paper-title'
        back = RETURN_TO.get(page.rsplit('/', 1)[-1], '')
        write_reader(dist, page, title, paper, author, outline(page, sections), content, heading_id,
                     back if back in targets else '', stylesheets)
    (dist / 'downloads').mkdir(exist_ok=True)
    shutil.copyfile(SOURCE / 'paper.tex', dist / 'downloads/eth-false.tex')
    return pages


def external_links(value):
    if isinstance(value, dict):
        if value.get('t') == 'Link' and urlsplit(value['c'][2][0]).netloc:
            yield value['c'][2][0]
        yield from external_links(value.get('c', []))
    elif isinstance(value, list):
        for child in value:
            yield from external_links(child)


if __name__ == '__main__':
    build(SOURCE.parents[1] / 'docs')

