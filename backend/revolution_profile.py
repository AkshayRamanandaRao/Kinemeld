"""Validate and integrate a simple radial/axial polygon for a full revolution."""
import math
import polygon_profile


def profile(vertices):
    polygon_profile.validate(vertices)
    if any(p['x'] < 0 for p in vertices):raise ValueError('Revolution radii must be nonnegative.')
    zeros=[i for i,p in enumerate(vertices) if p['x']==0]
    if zeros and sum(1 for i in zeros if (i-1)%len(vertices) not in zeros)>1:
        raise ValueError('The profile may touch the rotation axis in only one continuous boundary section.')
    origin=vertices[0]['y'];points=[(p['x'],p['y']-origin) for p in vertices]
    def moment(p,q):
        total=0.
        for (a,b),(c,d) in zip(points,points[1:]+points[:1]):
            cross=a*d-c*b
            for i in range(p+1):
                for j in range(q+1):
                    total+=cross*math.comb(p,i)*math.comb(q,j)*a**i*c**(p-i)*b**j*d**(q-j)*math.factorial(i+j)*math.factorial(p+q-i-j)/math.factorial(p+q+2)
        return total
    sign=1 if moment(0,0)>0 else -1
    radial=sign*moment(1,0);radial_z=sign*moment(1,1);radial_z2=sign*moment(1,2);radial3=sign*moment(3,0)
    if not math.isfinite(radial) or radial<=0 or radial3<=0:raise ValueError('Revolution profile must enclose positive volume.')
    axial=radial_z2-radial_z**2/radial
    if not math.isfinite(axial) or axial<=0:raise ValueError('Revolution inertia is invalid.')
    return {'volume':2*math.pi*radial,'z':origin+radial_z/radial,'axial':axial,'radial3':radial3}
