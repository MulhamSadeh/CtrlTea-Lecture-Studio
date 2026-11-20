"""Conservative geometry checks: reject ambiguous crossings; never reroute a graph."""

def check_geometry(spec):
    nodes={n.id:n for n in spec.nodes}
    routes=[]
    for e in spec.edges:
        pts=[nodes[e.start].port(e.start_port)]+[(p.x,p.y) for p in e.bends]+[nodes[e.end].port(e.end_port)]
        routes.append(list(zip(pts,pts[1:])))
    def bounds(n):
        rx,ry=(n.width/2,n.height/2) if n.kind=='block' else ((18,18) if n.kind=='sum' else (4,4))
        return n.x-rx,n.y-ry,n.x+rx,n.y+ry
    boxes={k:bounds(n) for k,n in nodes.items()}
    for i,a in enumerate(spec.nodes):
        l,t,r,b=boxes[a.id]
        for other in spec.nodes[i+1:]:
            ll,tt,rr,bb=boxes[other.id]
            if max(l,ll)<min(r,rr) and max(t,tt)<min(b,bb):
                raise ValueError('عقدتان متداخلتان؛ عدّل مواضعهما')
    for e,segments in zip(spec.edges,routes):
        for si,((x,y),(xx,yy)) in enumerate(segments):
            for k,(l,t,r,b) in boxes.items():
                if (k==e.start and si==0) or (k==e.end and si==len(segments)-1):continue
                if (abs(x-xx)<1e-6 and l<x<r and max(min(y,yy),t)<min(max(y,yy),b)) or (abs(y-yy)<1e-6 and t<y<b and max(min(x,xx),l)<min(max(x,xx),r)):
                    raise ValueError('مسار يمر عبر عقدة أخرى؛ عدّل bends')
    def contact(a,b):
        (x,y),(xx,yy)=a;(u,v),(uu,vv)=b
        l=max(min(x,xx),min(u,uu));r=min(max(x,xx),max(u,uu))
        t=max(min(y,yy),min(v,vv));bottom=min(max(y,yy),max(v,vv))
        if l>r+1e-6 or t>bottom+1e-6:return None
        if r-l>1e-6 or bottom-t>1e-6:return 'overlap'
        return (round(l,6),round(t,6))
    for i,segments in enumerate(routes):
        for j in range(i,len(routes)):
            shared=set((spec.edges[i].start,spec.edges[i].end)) & set((spec.edges[j].start,spec.edges[j].end))
            allowed={(round(nodes[k].x,6),round(nodes[k].y,6)) for k in shared if nodes[k].kind=='branch'} if i!=j else set()
            for ai,a in enumerate(segments):
                for bi,b in enumerate(routes[j]):
                    if i==j and bi<=ai:continue
                    hit=contact(a,b)
                    if hit is None:continue
                    if i==j and bi==ai+1 and hit!='overlap':continue
                    if hit not in allowed:
                        raise ValueError('تقاطع أو تراكب مسارات ملتبس؛ أعد توزيع المسارات أو عرّف branch صريحة')
