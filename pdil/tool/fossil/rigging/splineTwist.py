from __future__ import absolute_import, division, print_function

from collections import OrderedDict
import math

from pymel.core import curve, cluster, delete, dt, duplicate, expression, group, hide, ikHandle, insertKnotCurve, joint, move, orientConstraint, parent, parentConstraint, pointConstraint, xform

from ....add import simpleName, shortName
from .... import core
from .... import lib
from .... import nodeApi

from .. import controllerShape
from .. import space

from ..cardRigging import MetaControl, ParamInfo

from . import _util as util


class OrientMode:
    CLOSEST_JOINT = 'closest_joint'
    WORLD = 'world'
    AS_FIRST_JOINT = 'as_first_joint'


class TwistStyle:
    '''
    Used by splineIk.  Advanced uses advanced twist while the others determin
    which rotation axis drives the twist attribute.
    '''
    ADVANCED = 'Advanced'
    X        = 'X'
    NEG_X    = '-X'
    Y        = 'Y'
    NEG_Y    = '-Y'
    Z        = 'Z'
    NEG_Z    = '-Z'
    
    @classmethod
    def asChoices(cls):
        choices = OrderedDict()
        choices[cls.ADVANCED]   = cls.ADVANCED
        choices[cls.X]          = cls.X
        choices[cls.NEG_X]      = cls.NEG_X
        choices[cls.Y]          = cls.Y
        choices[cls.NEG_Y]      = cls.NEG_Y
        choices[cls.Z]          = cls.Z
        choices[cls.NEG_Z]      = cls.NEG_Z
        return choices


@util.adds('twist', 'stretch')
@util.defaultspec( {'shape': 'sphere', 'size': 10, 'color': 'blue 0.22'} )
def buildSplineTwist(start, end, controlCountOrCrv=4, twistInfDist=0, simplifyCurve=True,
    tipBend=True, sourceBend=True, matchOrient=True, allowOffset=True,  # noqa e128
    useLeadOrient=False,  # This is an backwards compatible option, mutually exclusive with matchOrient
    twistStyle=TwistStyle.ADVANCED, duplicateCurve=True,
    controlOrient=OrientMode.CLOSEST_JOINT,
    name='', groupName='', controlSpec={}):
    '''
    Make a spline controller from `start` to `end`.
    
    :param int twistInfDist: Default twist controls to falloff before hitting eachother.
        Otherwise it is the number of joints on either side it will influence.
    :param bool simplifyCurve:  Only used if # of cvs is specified.  Turning it
        on will likely result it the curve not matching the existing joint position
        but will be more evenly spaced per control.
    :param bool tipBend:  If True, an extra cv will be added at the second to
        last joint, controlled by the last controller to ease out.
        
    ##:param bool applyDirectly: If True, rig the given joints, do not make a duplicate chain
        
    :param bool useLeadOrient: If True, the controllers will be aligned the same
        as the first joint.
        **NOTE** I think this option only exists to preserve previous builds, this is pretty dumb
        
    :param bool matchOrient: Does trueZero on the start and end.  I'm not sure this makes sense.
        
    
    
    ..  todo::
        * Add the same spline chain +X towards child that the neck has and test out advancedTwist()
    
        * See if I can identify the closest joint to a control and orient to that
        * The first joint has parent AND local, which are the same thing, keep this for convenience of selecting all the controls and editing attrs?
        * Test specifying your own curve
        * There is a float division error that can happen if there are too many control cvs.
        * Verify twists work right with unsimplified curves (hint, I don't think they do).
    '''
    
    matchOrient = False
    useLeadOrient = False
    
    if isinstance( controlCountOrCrv, int ):
        assert controlCountOrCrv > 3, "controlCount must be at least 4"
    
    # The axis to twist and stretch on.
    jointAxis = util.identifyAxis( start.listRelatives(type='joint')[0] )
    
    # Make a duplicate chain for the IK that will also stretch.
    stretchingChain = util.dupChain( start, end, '{0}_stretch' )
    
    # &&& NOTE!  This might affect advanced twist in some way.
    # If the chain is mirrored, we need to reorient to point down x so the
    # spline doesn't mess up when the main control rotates
    if stretchingChain[1].tx.get() < 0:
        # Despite aggresive zeroing of the source, the dup can still end up slightly
        # off zero so force it.
        for jnt in stretchingChain:
            jnt.r.set(0, 0, 0)
        joint( stretchingChain[0], e=True, oj='xyz', secondaryAxisOrient='yup', zso=True, ch=True)
        joint( stretchingChain[-1], e=True, oj='none')
    
    if isinstance( controlCountOrCrv, int ):
        mainIk, _effector, crv = ikHandle( sol='ikSplineSolver',
            sj=stretchingChain[0],
            ee=stretchingChain[-1],
            ns=controlCountOrCrv - 3,
            simplifyCurve=simplifyCurve)
    else:
        if duplicateCurve:
            crv = duplicate(controlCountOrCrv)[0]
        else:
            crv = controlCountOrCrv
            
        mainIk, _effector = ikHandle( sol='ikSplineSolver',
            sj=stretchingChain[0],
            ee=stretchingChain[-1],
            ccv=False,
            pcv=False)
        crv.getShape().worldSpace[0] >> mainIk.inCurve
    
    hide(mainIk)
    mainIk.rename( simpleName(start, "{0}_ikHandle") )
    crv.rename( simpleName(start, "{0}_curve") )
        
    if not name:
        name = util.trimName(start)

    if name.count(' '):
        name, endName = name.split()
    else:
        endName = ''
    
    # Only add a tipBend cv if number of cvs was specified.
    if tipBend and isinstance( controlCountOrCrv, int ):
        currentTrans = [ xform(cv, q=True, ws=True, t=True) for cv in crv.cv ]
        insertKnotCurve( crv.u[1], nk=1, add=False, ib=False, rpo=True, cos=True, ch=True)
        for pos, cv in zip(currentTrans, crv.cv[:-2]):
            xform( cv, ws=True, t=pos )
    
        xform( crv.cv[-2], ws=True, t=xform(end.getParent(), q=True, ws=True, t=True) )
        xform( crv.cv[-1], ws=True, t=currentTrans[-1] )
        
    # Only add a sourceBend cv if number of cvs was specified.
    if sourceBend and isinstance( controlCountOrCrv, int ):
        currentTrans = [ xform(cv, q=True, ws=True, t=True) for cv in crv.cv ]
        insertKnotCurve( crv.u[1.2], nk=1, add=False, ib=False, rpo=True, cos=True, ch=True)  # I honestly don't know why, but 1.2 must be different than 1.0
        for pos, cv in zip(currentTrans[1:], crv.cv[2:]):
            xform( cv, ws=True, t=pos )
    
        xform( crv.cv[0], ws=True, t=currentTrans[0] )
        xform( crv.cv[1], ws=True, t=xform(stretchingChain[1], q=True, ws=True, t=True) )
    
    grp = group(em=True, p=lib.getNodes.mainGroup(), n=start.name() + "_splineTwist")
    
    controls = util.addControlsToCurve(name + 'Ctrl', crv, controlSpec['main'])
    for ctrl in controls:
        core.dagObj.zero(ctrl).setParent( grp )


    if controlOrient == OrientMode.CLOSEST_JOINT:
        # Use the real chain to match orientations since the stretching chain might reorient to compensate for mirroring.
        jointPos = {j: dt.Vector(xform(j, q=True, ws=True, t=True)) for j in util.getChain(start, end)}
        
        aveSpacing = util.chainLength(stretchingChain) / (len(stretchingChain) - 1)
        
        for ctrl in controls:
            cpos = dt.Vector(xform(ctrl, q=True, ws=True, t=True))
            distances = [ ( (jpos - cpos).length() / aveSpacing, j) for j, jpos in jointPos.items()  ]
            distances.sort()
            
            
            ''' Just use the closest joint if within 10% of the average spacing
            Possible future improvement, look at two joints, and determine if
            the control is between them and inbetween the orientation.
            '''
            if True:  # distances[0][0] < 100:
                r = xform(distances[0][1], q=True, ro=True, ws=True)

                with core.dagObj.Solo(ctrl):
                    xform(ctrl, ro=r, ws=True)
                    core.dagObj.zero(ctrl)
                    
            
            """
            # Otherwise split the distances by the percentages
            else:
                #m1 = xform(distances[0][1], q=True, m=True, ws=True)
                #m2 = xform(distances[1][1], q=True, m=True, ws=True)
                
                distA, jointA = distances[0]
                distB, jointB = distances[1]
                x, y, z = midOrient2(jointA, jointB)
                
                matrix = list(x) + [0] + list(y) + [0] + list(z) + [0] + xform(ctrl, q=True, ws=True, t=True) + [1.0]
                
                print( ctrl, 'to', jointA, jointB )
                with Solo(ctrl):
                    xform(ctrl, ws=True, m=matrix)
                    # Need to improve my matrix skills, for now it's easy enough to just rotate it
                    #rotate(ctrl, [0, 180, 0], os=1, r=1)
                    core.dagObj.zero(ctrl)
            """
                

    if endName:
        controls[-1].rename(endName + 'Ctrl')

    if matchOrient:
        util.trueZeroSetup(start, controls[0])
        util.trueZeroSetup(end, controls[-1])

    if tipBend:
        if useLeadOrient and not matchOrient:
            controls[-1].setRotation( end.getRotation(space='world'), space='world' )
        
        parent( controls[-2].getChildren(), controls[-1] )
        name = controls[-2].name()
        delete( core.dagObj.zero(controls[-2]) )

        if not endName:
            controls[-1].rename(name)
        controls[-2] = controls[-1]
        controls.pop()
        #core.dagObj.zero(controls[-2]).setParent(controls[-1])
        #channels = [t + a for t in 'trs' for a in 'xyz']
        #for channel in channels:
        #    controls[-2].attr( channel ).setKeyable(False)
        #    controls[-2].attr( channel ).lock()
           
    if sourceBend:
        names = []
        
        for ctrl in controls[1:-1]:
            names.append( ctrl.name() )
            ctrl.rename( '__temp' )
        
        endNum = -1 if endName else None
        for name, cur in zip(names, controls[2:endNum] ):
            cur.rename(name)
            
        if useLeadOrient and not matchOrient:
            controls[0].setRotation( start.getRotation(space='world'), space='world' )
            
        parent( controls[1].getChildren(), controls[0] )
        delete( core.dagObj.zero(controls[1]) )
        
        del controls[1]
        
    controls[0] = nodeApi.RigController.convert(controls[0])
    controls[0].container = grp
    
    stretchAttr, jointLenMultiplier = util.makeStretchySpline(controls[0], mainIk)
        
    connectingCurve = addConnectingCurve(controls)
    controls[0].visibility >> connectingCurve.visibility
    
    # Make twist for everything but hide them all and drive the ones that overlap
    # with spline controllers by the spline control.
    if not twistInfDist:
        numJoints = countJoints(start, end)
        twistInfDist = int(math.ceil( numJoints - len(controls) ) / float(len(controls) - 1))
        twistInfDist = max(1, twistInfDist)
    
    noInherit = group(em=True, p=grp, n='NoInheritTransform')
    core.dagObj.lockTrans(noInherit)
    core.dagObj.lockRot(noInherit)
    core.dagObj.lockScale(noInherit)
    noInherit.inheritsTransform.set(False)
    noInherit.inheritsTransform.lock()

    # &&& If simplify curve is ON, the last joint gets constrained to the spinner?
    # Otherwise it gets constrained to the offset or stretch joint, which I think is correct.
    
    if allowOffset:
        # If allowOffset, make another chain to handle the difference in joint positions.
        offsetChain = util.dupChain( start, end, '{0}_offset' )

        offsetChain[0].setParent(noInherit)
        hide(offsetChain[0])
        twists, constraints = addTwistControls( offsetChain, start, end, twistInfDist)
        finalRigJoint = offsetChain[-1]
    else:
        twists, constraints = addTwistControls( stretchingChain, start, end, twistInfDist )
        finalRigJoint = stretchingChain[-1]
    
    # Constrain the end to the last controller so it doesn't pop off at all,
    # but still respect the stretch attr.
    pointConstraint(finalRigJoint, end, e=True, rm=True)
    
    # Make a proxy that can allows respecting stretch being active or not.
    endProxy = duplicate(end, po=True)[0]
    endProxy.rename('endProxy')
    hide(endProxy)
    endProxy.setParent(grp)
    
    stretchAttr >> core.constraints.pointConst( controls[-1], endProxy, mo=True )
    core.math.opposite(stretchAttr) >> core.constraints.pointConst( finalRigJoint, endProxy )
    constraints.point >> core.constraints.pointConst( endProxy, end )
    
    hide(twists)
    
    numControls = len(controls)
    numTwists = len(twists)
    for i, ctrl in enumerate(controls):
        index = int(round( i * ((numTwists - 1) / (numControls - 1)) ))
        util.drive( ctrl, 'twist', twists[index].attr('r' + jointAxis) )
        space.add( ctrl, start.getParent(), 'local' )
    
    parents = [start.getParent()] + controls[:-1]
    
    stretchingChain[0].setParent(noInherit)
    crv.setParent(noInherit)
    hide(crv, stretchingChain[0])
    connectingCurve.setParent( noInherit )
    
    mainIk.setParent(grp)
    
    # Do not want to scale but let rotate for "fk-like" space mode
    for ctrl, _parent in zip(controls, parents):
        core.dagObj.lockScale( ctrl )
        
        if useLeadOrient:
            ctrl.setRotation( start.getRotation(space='world'), space='world' )
            core.dagObj.zero(ctrl)
        
        space.addWorld(ctrl)
        space.add( ctrl, _parent, 'parent')
    
    for i, ctrl in enumerate(controls[1:]):
        controls[0].subControl[str(i)] = ctrl
    
    # Must constrain AFTER controls (possibly) get orientd
    orientConstraint( controls[-1], finalRigJoint, mo=True )

    # Setup advanced twist
    if twistStyle == TwistStyle.ADVANCED:
        # &&& Test using advancedTwist() to replace the code beloew
        util.advancedTwist(stretchingChain[0], stretchingChain[1], controls[0], controls[-1], mainIk)
        '''
        startAxis = duplicate( start, po=True )[0]
        startAxis.rename( 'startAxis' )
        startAxis.setParent( controls[0] )
        
        endAxis = duplicate( start, po=True )[0]
        endAxis.rename( 'endAxis' )
        endAxis.setParent( controls[-1] )
        endAxis.t.set(0, 0, 0)
        
        mainIk.dTwistControlEnable.set(1)
        mainIk.dWorldUpType.set(4)
        startAxis.worldMatrix[0] >> mainIk.dWorldUpMatrix
        endAxis.worldMatrix[0] >> mainIk.dWorldUpMatrixEnd
        
        hide(startAxis, endAxis)
        '''
    else:
        if twistStyle == TwistStyle.X:
            controls[-1].rx >> mainIk.twist
        elif twistStyle == TwistStyle.NEG_X:
            core.math.multiply(controls[-1].rx, -1.0) >> mainIk.twist
            
        elif twistStyle == TwistStyle.Y:
            controls[-1].ry >> mainIk.twist
        elif twistStyle == TwistStyle.NEG_Y:
            core.math.multiply(controls[-1].ry, -1.0) >> mainIk.twist
            
        elif twistStyle == TwistStyle.Z:
            controls[-1].rz >> mainIk.twist
        elif twistStyle == TwistStyle.NEG_Z:
            core.math.multiply(controls[-1].rz, -1.0) >> mainIk.twist
        
        # To make .twist work, the chain needs to follow parent joint
        follow = group(em=True, p=grp)
        target = start.getParent()
        core.dagObj.matchTo(follow, stretchingChain[0])
        parentConstraint( target, follow, mo=1 )
        follow.rename(target + '_follow')
        stretchingChain[0].setParent(follow)
        
    # Constraint the offset (if exists) to the stretch last to account for any adjustments.
    if allowOffset:
        util.constrainAtoB(offsetChain[:-1], stretchingChain[:-1])
        pointConstraint(stretchingChain[-1], offsetChain[-1], mo=True)

    return controls[0], constraints


def addTwistControls(controlChain, boundChain, boundEnd, influenceDist=3):
    '''
    Put a rotation controller under each child of the controlChain to drive .rz
    of the boundChain.  They must both be the same size.
    
    :param Joint controlChain: The first joint of the controlling rig (ideally pruned)
    :param Joint boundChain: The first joint of joints being controlled by the spline.
    :param Joint boundEnd: The last joint in the bound chain, used to address possible branching.
    :param int influenceDist: How many adjacent joints are influenced (total #
        is 2x since it influences both directions).
    '''
    
    obj = controlChain[0]
    target = boundChain
    
    #controlJoints = getChain( controlChain, findChild(controlChain, shortName(boundEnd)) )
    controlJoints = controlChain
    boundJoints = util.getChain( boundChain, util.findChild(boundChain, shortName(boundEnd)) )
    
    assert len(controlJoints) == len(boundJoints), "Failure when adding twist controls, somehow the chains don't match length, contorls {0} != {1}".format( len(controlJoints), len(boundJoints) )
    
    controls = []
    groups = []

    pointConstraints = []
    orientConstraints = []
    
    for i, (obj, target) in enumerate(zip(controlJoints, boundJoints)):
    
        c = controllerShape.simpleCircle()
        c.setParent(obj)
        c.t.set(0, 0, 0)
        c.r.set(0, 0, 0)
        
        controls.append(c)
        
        spinner = group(em=True, name='spinner%i' % i, p=target)
        spinner.r.set(0, 0, 0)
        spinner.setParent(obj)
        spinner.t.set(0, 0, 0)
        
        # Aligning the spinners to the bound joint means we don't have to offset
        # the orientConstraint which means nicer numbers.
#        spinner.setRotation( target.getRotation(space='world'), space='world' )
        
        groups.append(spinner)

        pointConstraints.append( core.constraints.pointConst( obj, target, maintainOffset=False ) )
        orientConstraints.append( core.constraints.orientConst( spinner, target, maintainOffset=False ) )
        
        children = obj.listRelatives(type='joint')
        if children:
            obj = children[0]
        else:
            obj = None
            break
    
    for pSrc, pDest in zip( pointConstraints[:-1], pointConstraints[1:]):
        pSrc >> pDest
    
    for oSrc, oDest in zip( orientConstraints[:-1], orientConstraints[1:]):
        oSrc >> oDest
    
    # &&& This and the i+7 reflect the number of controls that influence
    bigList = [None] * influenceDist + controls + [None] * influenceDist
    
    influenceRange = (influenceDist * 2) + 1
    
    axis = util.identifyAxis(controlChain[0].listRelatives(type='joint')[0])
    
    exp = []
    for i, spinner in enumerate(groups):
        exp.append(driverExpression( spinner, bigList[i: i + influenceRange], axis ))
        
    expression( s=';\n'.join(exp) )
    
    return controls, util.ConstraintResults( pointConstraints[0], orientConstraints[0] )




class SplineTwist(MetaControl):
    ''' Spline IK that provides control to twist individual sections. '''
    ik_ = 'pdil.tool.fossil.rigging.splineTwist.buildSplineTwist'
    ikInput = OrderedDict( [
        ('controlCountOrCrv', [
            ParamInfo( 'CV count', 'How many cvs to use in auto generated curve', ParamInfo.INT, default=4, min=4 ),
            ParamInfo( 'Curve', 'A nurbs curve to use for spline', ParamInfo.NODE_0 ),
        ] ),
        ('simplifyCurve',
            ParamInfo( 'Simplify Curve', 'If True, the curve cvs will space out evenly, possibly altering the postions', ParamInfo.BOOL, default=True) ),
        ('twistInfDist',
            ParamInfo( 'Twist influence', 'How many joints on one side are influenced by the twisting, zero means it is done automatically.', ParamInfo.INT, default=0, min=0) ),
        ('tipBend',
            ParamInfo( 'Tip Bend', 'The tip control should influence the ease out bend', ParamInfo.BOOL, default=True) ),
        ('sourceBend',
            ParamInfo( 'Source Bend', 'The source control should influence the ease in bend', ParamInfo.BOOL, default=True) ),
        ('matchOrient',
            ParamInfo( 'Match Orient', "First and last controller are set to TrueZero'd", ParamInfo.BOOL, default=True) ),
        ('useLeadOrient',
            ParamInfo( 'Lead Orient', 'The controls have the same orientation as the first joint', ParamInfo.BOOL, default=False) ),
        ('allowOffset',
            ParamInfo( 'Allow Offset', 'If you Simplyify Curve, the joints will slightly shift unless you Allow Offset or the joints are straight', ParamInfo.BOOL, default=False) ),
        ('twistStyle',
            ParamInfo( 'Twist Style', '0 = advanced, 1=x, 2=-x 3=y ...', ParamInfo.ENUM, enum=TwistStyle.asChoices(), default=TwistStyle.ADVANCED ) ),
        
        ('name',
            ParamInfo( 'Name', 'Name', ParamInfo.STR, '')),
    ] )
    
    fkArgs = {'translatable': True}
    
    @classmethod
    def readIkKwargs(cls, card, isMirroredSide, sideAlteration=lambda **kwargs: kwargs, kinematicType='ik'):
        '''
        Overriden to handle if a custom curve was given, which then needs to be duplicated, mirrored and
        fed directly into the splineTwist.
        '''

        kwargs = cls.readKwargs(card, isMirroredSide, sideAlteration, kinematicType='ik')
        if isMirroredSide:
            if 'controlCountOrCrv' in kwargs and not isinstance( kwargs['controlCountOrCrv'], int ):
                crv = kwargs['controlCountOrCrv']
                crv = duplicate(crv)[0]
                kwargs['controlCountOrCrv'] = crv
                move( crv.sp, [0, 0, 0], a=True )
                move( crv.rp, [0, 0, 0], a=True )
                crv.sx.set(-1)
                
                kwargs['duplicateCurve'] = False
                
        return kwargs








def addConnectingCurve(objs):
    '''
    Given a list of objects, make a curve that links all of them.
    '''
    crv = curve( d=1, p=[(0, 0, 0)] * len(objs) )

    grp = group(crv, n='connectingCurve')

    for i, obj in enumerate(objs):
        handle = cluster(crv.cv[i])[1]
        pointConstraint( obj, handle )
        handle.setParent( grp )
        hide(handle)
        
    crv.getShape().overrideEnabled.set( 1 )
    crv.getShape().overrideDisplayType.set( 2 )
        
    return grp


def countJoints(start, end):
    count = 2
    
    p = end.getParent()
    
    while p and p != start:
        p = p.getParent()
        count += 1
        
    if not p:
        return 0
        
    return count


def driverExpression( driven, controls, axis ):
    '''
    The `driven` node's .rz will be driven by the list of `controls`.
    `controls` is a list of objects, and optional empty entries.
    
    Example, if you have joints, A B C and controls X Y Z, you would do:
        driverExpression( A, [None, X, Y] )
        driverExpression( B, [X, Y, Z] )
        driverExpression( C, [Y, Z, None] )
    
    This means A will be fully influenced by X, and partially by Y.
    B is fully influenced by Y and partially by X and Z.
    '''
    
    powers = calcInfluence(controls)
    exp = []
    for power, ctrl in zip(powers, controls):
        if ctrl:
            exp.append( '{0}.r{axis} * {1}'.format(ctrl, power, axis=axis) )
    
    return '{0}.r{axis} = {1};'.format( driven, ' + '.join(exp), axis=axis )



def calcInfluence( controls ):
    '''
    Given a list (Maybe change to a number?) returns a list of power falloffs.
    
    controls can have None placeholders
    
    power falls off to end of controls
    low   upper
      v   v
    0 1 2 3 4
    # Result: [0.5, 0.75, 1.0, 0.75, 0.5]
    
    low     upper
      v     v
    0 1 2 3 4 5
    # Result: [0.5, 0.75, 1.0, 1.0, 0.75, 0.5]
    
    '''
    max = len(controls)
    if len(controls) % 2 == 0:
        upper = int(len(controls) / 2 + 1)
        lower = upper - 2
    else:
        upper = int(len(controls) / 2 + 1)
        lower = upper - 1
        
    delta = 1 / float(lower) * 0.5
        
    powers = [1.0] * len(controls)
    #for i, (lowCtrl, upCtrl) in enumerate(zip(controls[upper:], reversed(controls[:lower]) ), 1):
    for i, (lowCtrl, upCtrl) in enumerate(zip(range(upper, max), range( lower - 1, -1, -1 ) ), 1):
        power = 1 - delta * i
        powers[lowCtrl] = power
        powers[upCtrl] = power

    return powers
