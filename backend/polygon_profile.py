"""Validate a bounded simple XY polygon and return its area centroid."""
import math


def validate(vertices):
    if not isinstance(vertices,list) or not 3 <= len(vertices) <= 64:
        raise ValueError('Provide 3 to 64 distinct profile vertices.')
    points=[]
    for item in vertices:
        if not isinstance(item,dict) or set(item)!={'x','y'}:
            raise ValueError('Each profile vertex must contain exactly x and y.')
        xy=[]
        for key in ('x','y'):
            value=item[key]
            if type(value) not in (int,float) or abs(value)>1000 or not math.isfinite(value):
                raise ValueError('Profile coordinates must be finite and within ±1000 m.')
            xy.append(value)
        points.append(xy)
    scale=max(max(p[i] for p in points)-min(p[i] for p in points) for i in (0,1))
    if scale<=1e-9:raise ValueError('Profile must have nonzero size.')
    eps=1e-12*scale*scale
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on_segment(a,b,p):return min(a[0],b[0])-1e-12*scale<=p[0]<=max(a[0],b[0])+1e-12*scale and min(a[1],b[1])-1e-12*scale<=p[1]<=max(a[1],b[1])+1e-12*scale
    def intersects(a,b,c,d):
        o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
        if ((o1>eps and o2 < -eps) or (o1 < -eps and o2>eps)) and ((o3>eps and o4 < -eps) or (o3 < -eps and o4>eps)):return True
        return any(abs(o)<=eps and on_segment(x,y,p) for o,x,y,p in ((o1,a,b,c),(o2,a,b,d),(o3,c,d,a),(o4,c,d,b)))
    n=len(points)
    for i,a in enumerate(points):
        b=points[(i+1)%n]
        if math.hypot(b[0]-a[0],b[1]-a[1])<=1e-9*scale:raise ValueError('Profile edges must have distinct endpoints.')
        c=points[(i+2)%n]
        if abs(orient(a,b,c))<=eps and (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1])<0:
            raise ValueError('Adjacent profile edges must not overlap.')
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            if intersects(a,b,points[j],points[(j+1)%n]):raise ValueError('Profile edges must not intersect or touch.')
    origin=points[0];shifted=[(x-origin[0],y-origin[1]) for x,y in points]
    terms=[(x*y2-x2*y,x,y,x2,y2) for (x,y),(x2,y2) in zip(shifted,shifted[1:]+shifted[:1])]
    twice=sum(t[0] for t in terms)
    if abs(twice)<=2*eps:raise ValueError('Profile area is too small or degenerate.')
    cx=sum(c*(x+x2) for c,x,y,x2,y2 in terms)/(3*twice)+origin[0]
    cy=sum(c*(y+y2) for c,x,y,x2,y2 in terms)/(3*twice)+origin[1]
    return (cx,cy)
