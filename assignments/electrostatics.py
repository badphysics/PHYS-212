
# coding: utf-8

# In[ ]:

#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""electrostatics.py - classes for electrostatics problems

classes:
PointCharge
LineCharge
FieldLine
ElectricField
GaussianCircle
Equipotentials
"""
import io, os, sys, types

from IPython import get_ipython
from nbformat import read
from IPython.core.interactiveshell import InteractiveShell
import functools

import numpy
from numpy import array, arange, linspace, meshgrid, zeros_like, ones_like
from numpy import log10, sin, cos, arctan2, arccos, sqrt, fabs, cumsum
from numpy import radians, pi, infty
from numpy import dot, cross
from numpy import alltrue, isclose
from numpy import where, insert
from numpy import newaxis
from numpy.linalg import det

from scipy.integrate import ode
from scipy.interpolate import splrep, splev

import matplotlib
from matplotlib import pyplot as plt

# The area of interest
XMIN, XMAX = None, None
YMIN, YMAX = None, None
ZOOM = None
XOFFSET = None


#-----------------------------------------------------------------------------
# Decorators

def arrayargs(func):
    """Ensures all args are arrays."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """Ensures all args are arrays."""
        # pylint: disable=star-args
        return func(*[array(a) for a in args], **kwargs)
    return wrapper


#-----------------------------------------------------------------------------
# Functions

# pylint: disable=too-many-arguments
def init(xmin, xmax, ymin, ymax, zoom=1, xoffset=0):
    """Initializes the domain."""
    # pylint: disable=global-statement
    global XMIN, XMAX, YMIN, YMAX, ZOOM, XOFFSET
    XMIN, XMAX, YMIN, YMAX, ZOOM, XOFFSET =       xmin, xmax, ymin, ymax, zoom, xoffset

def norm(x):
    """Returns the magnitude of the vector x."""
    return sqrt(numpy.sum(array(x)**2, axis=-1))

@arrayargs
def point_line_distance(x0, x1, x2):
    """Finds the shortest distance between the point x0 and the line x1 to x2.
    Ref: http://mathworld.wolfram.com/Point-LineDistance3-Dimensional.html"""
    assert x1.shape == x2.shape == (2,)
    return fabs(cross(x0-x1, x0-x2))/norm(x2-x1)

@arrayargs
def angle(x0, x1, x2):
    """Returns angle between three points.
    Ref: https://stackoverflow.com/questions/1211212"""
    assert x1.shape == x2.shape == (2,)
    a, b = x1 - x0, x1 - x2
    return arccos(dot(a, b)/(norm(a)*norm(b)))

@arrayargs
def is_left(x0, x1, x2):
    """Returns True if x0 is left of the line between x1 and x2,
    False otherwise.  Ref: https://stackoverflow.com/questions/1560492"""
    assert x1.shape == x2.shape == (2,)
    matrix = array([x1-x0, x2-x0])
    if len(x0.shape) == 2:
        matrix = matrix.transpose((1, 2, 0))
    return det(matrix) > 0

def lininterp2(x1, y1, x):
    """Linear interpolation at points x between numpy arrays (x1, y1).
    Only y1 is allowed to be two-dimensional.  The x1 values should be sorted
    from low to high.  Returns a numpy.array of y values corresponding to
    points x.
    """
    return splev(x, splrep(x1, y1, s=0, k=1))

def finalize_plot():
    """Finalizes the plot."""
    ax = plt.axes()
    ax.set_xticks([])
    ax.set_yticks([])
    plt.xlim(XMIN/ZOOM+XOFFSET, XMAX/ZOOM+XOFFSET)
    plt.ylim(YMIN/ZOOM, YMAX/ZOOM)
    plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)


#-----------------------------------------------------------------------------
# Classes

class PointCharge:
    """A point charge.  This constructs a point charge.
        for example:
            PointCharge(1.0e-10,[0,0])

            This command constructs a point charge of charge 1.0e-10 C at the origin
    """

    R = 0.01  # The effective radius of the charge

    def __init__(self, q, x):
        """Initializes the quantity of charge 'q' and position vector 'x'."""
        self.q, self.x = q, array(x)
        self.type = 'Point'

    def E(self, x):  # pylint: disable=invalid-name
        """Electric field vector at a point x

        use: charge.E([1,1])
            gives the electric field at the point [1,1] due to charge where charge
            is defined as a point charge

        """
        if self.q == 0:
            return 0
        else:
            dx = x-self.x
            return (1.0/(4*pi*8.85e-12))*(self.q*dx.T/numpy.sum(dx**2, axis=-1)**1.5).T

    def V(self, x):  # pylint: disable=invalid-name
        """Potential due to a point charge

            This function takes in a point x to evaluate the potential at
        """
        k=9e9
        return k*self.q/norm(x-self.x)

    def is_close(self, x):
        """Returns True if x is close to the charge; false otherwise."""
        return norm(x-self.x) < self.R

    def plot(self):
        """Plots the charge."""
        color = 'b' if self.q < 0 else 'r' if self.q > 0 else 'k'
        r = 0.1*(sqrt(fabs(self.q))/2 + 1)
        circle = plt.Circle(self.x, r, color=color, zorder=10)
        plt.gca().add_artist(circle)


class PointChargeFlatland(PointCharge):
    """A point charge in Flatland.
    Ref: https://physics.stackexchange.com/questions/44515"""

    def E(self, x):  # pylint: disable=invalid-name
        """Electric field vector."""
        dx = x-self.x
        return (self.q*dx.T/numpy.sum(dx**2, axis=-1)).T

    def V(self, x):
        raise RuntimeError('Not implemented')


class LineCharge:
    """A line charge.
       Use:
        LineCharge(1.0,[1,0],[2,0])

        This produces a line of charge, 1.0 C, distributed uniformly from
        [1,0] to [2,0].
    """

    R = 0.01  # The effective radius of the charge

    def __init__(self, q, x1, x2):
        """Initializes the quantity of charge 'q' and end point vectors
        'x1' and 'x2'."""
        self.q, self.x1, self.x2 = q, array(x1), array(x2)
        self.type = 'Line'
    def get_lam(self):
        """Returns the charge density of the line."""
        return self.q / norm(self.x2 - self.x1)
    lam = property(get_lam)

    def E(self, x):  # pylint: disable=invalid-name
        """Electric field vector at a point x

            Use:  LineCharge.E(x)

        Ref: http://www.phys.uri.edu/gerhard/PHY204/tsl31.pdf
        """
        x = array(x)
        x1, x2, lam = self.x1, self.x2, self.lam

        # Get lengths and angles for the different triangles
        theta1, theta2 = angle(x, x1, x2), pi - angle(x, x2, x1)
        a = point_line_distance(x, x1, x2)
        r1, r2 = norm(x - x1), norm(x - x2)

        # Calculate the parallel and perpendicular components
        sign = where(is_left(x, x1, x2), 1, -1)

        # pylint: disable=invalid-name
        Epara = (1.0/(4.0*pi*8.85e-12))*lam*(1/r2-1/r1)
        Eperp = -(1.0/(4.0*pi*8.85e-12))*sign*lam*(cos(theta2)-cos(theta1))/where(a == 0, infty, a)

        # Transform into the coordinate space and return
        dx = x2 - x1

        if len(x.shape) == 2:
            Epara = Epara[::, newaxis]
            Eperp = Eperp[::, newaxis]

        return Eperp * (array([-dx[1], dx[0]])/norm(dx)) + Epara * (dx/norm(dx))

    def is_close(self, x):
        """Returns True if x is close to the charge."""

        theta1 = angle(x, self.x1, self.x2)
        theta2 = angle(x, self.x2, self.x1)

        if theta1 < radians(90) and theta2 < radians(90):
            return point_line_distance(x, self.x1, self.x2) < self.R
        else:
            return numpy.min([norm(self.x1-x), norm(self.x2-x)], axis=0) <               self.R

    def plot(self):
        """Plots the charge."""
        color = 'b' if self.q < 0 else 'r' if self.q > 0 else 'k'
        x, y = zip(self.x1, self.x2)
        width = 5*(sqrt(fabs(self.lam))/2 + 1)
        plt.plot(x, y, color, linewidth=width)


# pylint: disable=too-few-public-methods
class FieldLine:
    """A Field Line."""

    def __init__(self, x):
        "Initializes the field line points 'x'."""
        self.x = x

    def plot(self, linewidth=None, startarrows=True, endarrows=True):
        """Plots the field line and arrows."""

        if linewidth == None:
            linewidth = matplotlib.rcParams['lines.linewidth']

        x, y = zip(*self.x)
        plt.plot(x, y, '-k', linewidth=linewidth)

        n = int(len(x)/2) if len(x) < 225 else 75
        if startarrows:
            plt.arrow(x[n], y[n], (x[n+1]-x[n])/200., (y[n+1]-y[n])/200.,
                         fc="k", ec="k",
                         head_width=0.1*linewidth, head_length=0.1*linewidth)

        if len(x) < 225 or not endarrows:
            return

        plt.arrow(x[-n], y[-n],
                     (x[-n+1]-x[-n])/100., (y[-n+1]-y[-n])/100.,
                     fc="k", ec="k",
                     head_width=0.1*linewidth, head_length=0.1*linewidth)


class ElectricField:
    """The electric field owing to a collection of charges."""

    dt0 = 0.01  # The time step for integrations

    def __init__(self, charges):
        """Initializes the field given 'charges'."""
        self.charges = charges

    def vector(self, x):
        """Returns the field vector."""
        return numpy.sum([charge.E(x) for charge in self.charges], axis=0)

    def magnitude(self, x):
        """Returns the magnitude of the field vector."""
        return norm(self.vector(x))

    def angle(self, x):
        """Returns the field vector's angle from the x-axis (in radians)."""
        return arctan2(*(self.vector(x).T[::-1])) # arctan2 gets quadrant right

    def direction(self, x):
        """Returns a unit vector pointing in the direction of the field."""
        v = self.vector(x)
        return (v.T/norm(v)).T

    def projection(self, x, a):
        """Returns the projection of the field vector on a line at given angle
        from x-axis."""
        return self.magnitude(x) * cos(a - self.angle(x))

    def line(self, x0):
        """Returns the field line passing through x0.
        Refs: http://folk.uib.no/fcihh/seminar/lec1.pdf and lect2.pdf
              http://numbercrunch.de/blog/2013/05/visualizing-streamlines/
        and especially: "Electric field lines don't work",
        http://scitation.aip.org/content/aapt/journal/ajp/64/6/10.1119/1.18237
        """

        if None in [XMIN, XMAX, YMIN, YMAX]:
            raise ValueError('Domain must be set using init().')

        # Set up integrator for the field line
        streamline = lambda t, y: list(self.direction(y))
        solver = ode(streamline).set_integrator('vode')

        # Initialize the coordinate lists
        x = [x0]

        # Integrate in both the forward and backward directions
        dt = 0.008

        # Solve in both the forward and reverse directions
        for sign in [1, -1]:

            # Set the starting coordinates and time
            solver.set_initial_value(x0, 0)

            # Integrate field line over successive time steps
            while solver.successful():

                # Find the next step
                solver.integrate(solver.t + sign*dt)

                # Save the coordinates
                if sign > 0:
                    x.append(solver.y)
                else:
                    x.insert(0, solver.y)

                # Check if line connects to a charge
                flag = False
                for c in self.charges:
                    if c.is_close(solver.y):
                        flag = True
                        break

                # Terminate line at charge or if it leaves the area of interest
                if flag or not (XMIN < solver.y[0] < XMAX) or                   not YMIN < solver.y[1] < YMAX:
                    break

        return FieldLine(x)

    def plot(self, nmin=-3.5, nmax=1.5):
        """Plots the field magnitude."""
        x, y = meshgrid(
            linspace(XMIN/ZOOM+XOFFSET, XMAX/ZOOM+XOFFSET, 200),
            linspace(YMIN/ZOOM, YMAX/ZOOM, 200))
        z = zeros_like(x)
        for i in range(x.shape[0]):
            for j in range(x.shape[1]):
                z[i, j] = log10(self.magnitude([x[i, j], y[i, j]]))
        levels = arange(nmin, nmax+0.2, 0.2)
        cmap = plt.cm.get_cmap('plasma')

        #pyplot.contourf(x, y, numpy.clip(z, nmin, nmax),
        #                10, cmap=cmap, levels=levels, extend='both')


# pylint: disable=too-few-public-methods
class GaussianCircle:
    """A Gaussian circle with radius r."""

    def __init__(self, x, r, a0=0):
        """Initializes the Gaussian surface at position vector 'x'
        and given radius 'r'.  'a0' defines an offset angle CCW from the
        x-axis.  Use this to identify the axis around which flux points should
        be symmetric."""
        self.x = x
        self.r = r
        self.a0 = a0

    def fluxpoints(self, field, n, uniform=False):
        """Returns points where field lines should enter/exit the surface.

        The flux points are usually chosen so that they are equally separated
        in electric field flux.  However, if 'uniform' is True then the points
        are equispaced.

        This method requires that the flux be in xor out everywhere on the
        circle (unless 'uniform' is True)."""

        # Create a dense array of points around the circle
        a = radians(linspace(0, 360, 1001)) + self.a0
        assert len(a)%4 == 1
        x = self.r*array([cos(a), sin(a)]).T + self.x

        if uniform:
            flux = ones_like(a)

        else:
            # Get the flux through each point.  Ensure the fluxes are either
            # all in or all out.
            flux = field.projection(x, a)

            if numpy.sum(flux) < 0:
                flux *= -1
            assert alltrue(flux > 0)

        # Create an integrated flux curve
        intflux = insert(cumsum((flux[:-1]+flux[1:])/2), 0, 0)
        assert isclose(intflux[-1], numpy.sum(flux[:-1]))

        # Divide the integrated flux curve into n+1 portions, and calculate
        # the corresponding angles.
        v = linspace(0, intflux[-1], n+1)
        a = lininterp2(intflux, a, v)[:-1]

        return self.r*array([cos(a), sin(a)]).T + self.x

class Equipotentials:
    """Equipotential Lines"""

    R = 0.01  # The effective radius of the charge

    def __init__(self, charges, X, Y):
        """Initializes the quantity of charge 'q' and end point vectors
        'x1' and 'x2'."""
        self.charges, self.X, self.Y = charges, X, Y
        self.type = 'Line'

    def potential_grid(self):
        V = 0.0*self.X
        N=200
        k=9e9
        for charge in self.charges:
            if charge.type == 'Line':

                lam = charge.get_lam()
                dx = (charge.x2[0]-charge.x1[0])/N#norm((array(charge.x1) - array(charge.x1)).tolist())/N
                dy = (charge.x2[1]-charge.x1[1])/N#norm((array(charge.x2) - array(charge.x1)).tolist())/N
                for i in range(N):
                    V+=k*lam*dx/sqrt((charge.x1[0]+dx*i-self.X)**2+(charge.x1[1]+dy*i-self.Y)**2)
            elif charge.type == 'Point':

                V += k*charge.q/sqrt((self.X-charge.x[0])**2+(self.Y-charge.x[1])**2)
        return V

    def potential_point(self,x,N=2000):
        V = 0

        k=9e9
        for charge in self.charges:
            if charge.type == 'Point':
                V+= charge.V(x)
            elif charge.type == 'Line':
                lam = charge.get_lam()
                dx = norm((array(charge.x2) - array(charge.x1)).tolist())/N
                for i in range(N):
                    V+=k*lam*dx/sqrt((charge.x1[0]+dx*i-x[0])**2+(x[1])**2)
        return V





# In[ ]:


# charges=[PointCharge(1e-19,[-1,0]),PointCharge(-1e-19,[1,0]),PointCharge(1.0e-19,[0,1])]

# x = linspace(-3.5, 3.5, 50)
# y = linspace(-3.5, 3.5, 50)

# Y,X = meshgrid(x,y)

# charges2 = [LineCharge(1,[.5,0],[1.5,0]),PointCharge(-2,[-1,0])]

# M=20
# vmin=-5
# vmax=5
# dx = (vmax-vmin)/M
# scale = 1.0e9
# cmaprange=[(vmin+i*dx)*scale for i in range(M)]


# In[ ]:



# VV = Equipotentials(charges,X,Y)

# V4 = VV.potential_grid()
# print(VV.potential_point([0,0]))
# scale = 1.0e-9
# cmaprange=[(vmin+i*dx)*scale for i in range(M)]

# CS = plt.contour(X, Y,V4,cmaprange)# V3,(np.array([-10,-5,-4,-3,-2,-1,-.8,-.6,-.4,-.2,-.1,0,.1,.2,.4,.6,.8,1,2,3,4,5,10])*1.0e9).tolist())
# #plt.clabel(CS, fontsize=3, inline=1)
# cbar = plt.colorbar(CS)
# plt.show()


# In[ ]:


# VV1 = Equipotentials(charges2,X,Y)

# V1 = VV1.potential_grid()
# print(VV1.potential_point([0,0]))
# scale = 1.0e9
# M=50
# vmin=-20
# cmaprange=[(vmin+i*dx)*scale for i in range(M)]

# CS = plt.contour(X, Y,V1,cmaprange)# V3,(np.array([-10,-5,-4,-3,-2,-1,-.8,-.6,-.4,-.2,-.1,0,.1,.2,.4,.6,.8,1,2,3,4,5,10])*1.0e9).tolist())
# #plt.clabel(CS, fontsize=3, inline=1)
# cbar = plt.colorbar(CS)
# plt.show()


# In[ ]:


# charges3=[LineCharge(1.0,[-1,0],[1,0]),PointCharge(-1.0,[0,1])]
# x = linspace(-2, 2, 50)
# y = linspace(-1, 2, 50)
# M=50
# dx = dx*2
# X,Y = meshgrid(x,y)
# VV3 = Equipotentials(charges3,X,Y)
# V3 = VV3.potential_grid()
# cmaprange=[(vmin+i*dx)*scale for i in range(M-10)]
# CS = plt.contour(X, Y,V3,cmaprange)# V3,(np.array([-10,-5,-4,-3,-2,-1,-.8,-.6,-.4,-.2,-.1,0,.1,.2,.4,.6,.8,1,2,3,4,5,10])*1.0e9).tolist())
# #plt.clabel(CS, fontsize=3, inline=1)
# cbar = plt.colorbar(CS)
# plt.show()


# In[ ]:


# charges4=[LineCharge(1.0,[-1,-.5],[1,-.5]),LineCharge(-1.0,[-1,.5],[1,.5])]
# x = linspace(-2, 2, 50)
# y = linspace(-2, 2, 50)
# M=100
# vmin=-1
# vmax=1.25
# scale=9e9
# dx = 2*(vmax-vmin)/M
# X,Y = meshgrid(x,y)
# VV4 = Equipotentials(charges4,X,Y)
# V4 = VV4.potential_grid()
# cmaprange=[(vmin+i*dx)*scale for i in range(M)]
# CS = plt.contour(X, Y,V4,cmaprange)# V3,(np.array([-10,-5,-4,-3,-2,-1,-.8,-.6,-.4,-.2,-.1,0,.1,.2,.4,.6,.8,1,2,3,4,5,10])*1.0e9).tolist())
# #plt.clabel(CS, fontsize=3, inline=1)
# cbar = plt.colorbar(CS)
# plt.show()
