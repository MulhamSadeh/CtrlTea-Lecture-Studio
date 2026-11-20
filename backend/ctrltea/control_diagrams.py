"""Opt-in, black vector control diagrams. No inference of topology or routing."""
from io import BytesIO
from lxml import etree
from matplotlib import mathtext, rc_context
from .models import ControlDiagram


def math_vector(value, prefix):
    # MathText is a local parser, never TeX or a shell. SVG glyphs work without fonts.
    if '$' in value:
        raise ValueError("اكتب math دون محددات الدولار")
    stream = BytesIO()
    with rc_context({'svg.fonttype': 'path', 'text.usetex': False}):
        mathtext.math_to_image('$'+value+'$', stream, format='svg', color='black')
    root=etree.fromstring(stream.getvalue())
    w,h=map(float,root.attrib['viewBox'].split()[2:])
    for el in root.iter():
        if 'id' in el.attrib:
            el.attrib['id']=prefix+el.attrib['id']
        for attr,v in list(el.attrib.items()):
            if attr.endswith('href') and v.startswith('#'):el.attrib[attr]='#'+prefix+v[1:]
            elif 'url(#' in v:el.attrib[attr]=v.replace('url(#','url(#'+prefix)
    # Matplotlib's axes patch is an opaque white background, omit it.
    for el in list(root.iter()):
        if el.attrib.get('id')==prefix+'patch_1':el.getparent().remove(el)
    return ''.join(etree.tostring(e,encoding='unicode') for e in root),w,h


def diagram(spec: ControlDiagram):
    from .figures import label_vector
    nodes={n.id:n for n in spec.nodes}
    bounds=[]; routes=[]
    for e in spec.edges:
        points=[nodes[e.start].port(e.start_port)]+[(p.x,p.y) for p in e.bends]+[nodes[e.end].port(e.end_port)]
        routes.append(points); bounds+=points
    for n in spec.nodes:
        w,h=(n.width,n.height) if n.kind=='block' else ((120,70) if n.kind in ('input','output') else (66,66))
        bounds.extend([(n.x-w/2,n.y-h/2),(n.x+w/2,n.y+h/2)])
        if n.tag: bounds.append((n.x-65,n.y-65))
    xmin=min(x for x,y in bounds)-15;ymin=min(y for x,y in bounds)-15
    width=max(x for x,y in bounds)+15-xmin;height=max(y for x,y in bounds)+15-ymin
    result=[f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="{xmin} {ymin} {width} {height}">',
            ]
    for i,(e,points) in enumerate(zip(spec.edges,routes)):
        coords=' '.join(f'{x},{y}' for x,y in points)
        result.append(f'<polyline data-edge="{i}" points="{coords}" fill="none" stroke="black" stroke-width="1.8"/>')
        x,y=points[-1];px,py=points[-2]
        length=((x-px)**2+(y-py)**2)**0.5
        ux,uy=(x-px)/length,(y-py)/length
        bx,by=x-7*ux,y-7*uy
        result.append(f'<path data-arrow="{i}" d="M{x},{y} L{bx-3.5*uy},{by+3.5*ux} L{bx+3.5*uy},{by-3.5*ux} Z" fill="black"/>')
        if e.sign:
            x,y=points[-1]; side=e.end_port
            dx,dy={'left':(-12,-12),'right':(12,-12),'top':(12,-12),'bottom':(12,18),'lower_left':(-12,18),'lower_right':(12,18)}[side]
            x+=dx;y+=dy
            result.append(f'<path data-sign="{e.sign}" d="M{x-4},{y} h8'+(f' M{x},{y-4} v8' if e.sign=='+' else '')+'" stroke="black" stroke-width="1.6"/>')
    for i,n in enumerate(spec.nodes):
        result.append(f'<g data-node="{n.id}" data-kind="{n.kind}">')
        if n.kind=='sum':
            result.append(f'<circle cx="{n.x}" cy="{n.y}" r="18" fill="none" stroke="black" stroke-width="1.8"/><path d="M{n.x-11},{n.y-11} l22,22 M{n.x-11},{n.y+11} l22,-22" stroke="black" stroke-width="1.8"/>')
        elif n.kind=='branch':result.append(f'<circle cx="{n.x}" cy="{n.y}" r="3.5" fill="black"/>')
        else:
            if n.kind=='block':result.append(f'<rect x="{n.x-n.width/2}" y="{n.y-n.height/2}" width="{n.width}" height="{n.height}" fill="none" stroke="black" stroke-width="1.8"/>')
            if n.math:
                content,w,h=math_vector(n.math,f'm{i}-');scale=min(3.2,(n.width-16)/w,(n.height-16)/h)
            else:
                w=n.width-12;root,h=label_vector(n.label,w,'black',f'l{i}-',size=18);content=etree.tostring(root,encoding='unicode');scale=1
                if h>n.height-8:raise ValueError('التسمية تتجاوز ارتفاع العقدة؛ كبّر أبعادها')
            y=n.y-h*scale/2 if n.kind=='block' else n.y-h*scale-12
            result.append(f'<g transform="translate({n.x-w*scale/2},{y}) scale({scale})">{content}</g>')
        if n.tag:
            root,h=label_vector(n.tag,55,'black',f't{i}-',size=16)
            if h>45: raise ValueError('تسمية خارجية طويلة؛ اختصر tag')
            result.append(f'<g transform="translate({n.x-62},{n.y-60})">'+etree.tostring(root,encoding='unicode')+'</g>')
        result.append('</g>')
    result.append('</svg>')
    return ''.join(result)
