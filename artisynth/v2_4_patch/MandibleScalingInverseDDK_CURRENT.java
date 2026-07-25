package artisynth.models.dynjaw;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.Locale;

import artisynth.core.inverse.TargetPoint;
import artisynth.core.inverse.TrackingController;
import artisynth.core.mechmodels.AxialSpring;
import artisynth.core.mechmodels.Collidable;
import artisynth.core.mechmodels.CollisionBehavior;
import artisynth.core.mechmodels.ExcitationComponent;
import artisynth.core.mechmodels.FrameMarker;
import artisynth.core.mechmodels.MechModel;
import artisynth.core.mechmodels.MultiPointMuscle;
import artisynth.core.mechmodels.MultiPointSpring;
import artisynth.core.mechmodels.RigidBody;
import artisynth.core.modelbase.CompositeComponent;
import artisynth.core.modelbase.ControllerBase;
import artisynth.core.modelbase.ModelComponent;
import artisynth.core.util.ArtisynthPath;
import artisynth.core.workspace.DriverInterface;
import maspack.matrix.Point3d;
import maspack.matrix.SymmetricMatrix3d;
import maspack.matrix.Vector3d;

/**
 * Corrected, isolated ArtiSynth inverse-tracking model for the canonical
 * mandibular mass-and-inertia rerun.
 *
 * <p>This class deliberately has a new name. It does not replace or overwrite
 * the archived MandibleScalingInverseDDK class. Geometry is fixed; gravity is
 * disabled; mandibular mass and rotational inertia scale as s^3 and s^5.
 * Maximum muscle force is fixed in fixed_force and is touched/scaled as s^2
 * only in force_capacity_s2.</p>
 *
 * <p>The requested amplitude A is peak-to-peak. For tau=t-t_settle, the active
 * z displacement is 0.5*A*(sin(omega*tau)-1), whose exact derivative is
 * 0.5*A*omega*cos(omega*tau). The factor 0.5 is required in both expressions.</p>
 */
public class MandibleScalingInverseDDK_CURRENT extends JawDemo {

  private static final String SPEC_VERSION =
      "ARTISYNTH_CANONICAL_2026-07-20_D8_TARGET_DERIVATIVE_COLLISION_API_V2";
  private static final String POSITION_FORMULA_ID =
      "P2P_ONE_SIDED_SIN_ACTIVE_V1";
  private static final String VELOCITY_FORMULA_ID =
      "P2P_ONE_SIDED_SIN_EXACT_DERIVATIVE_V1";
  private static final String CONTROLLER_ARCHITECTURE_ID =
      "TrackingController_point_target_LI_L2_excitation_damping_V1";

  private static final double CANONICAL_MASS_EXP = 3.0;
  private static final double CANONICAL_INERTIA_EXP = 5.0;
  private static final double CANONICAL_DURATION_S = 4.0;
  private static final double CANONICAL_SETTLE_S = 0.5;
  private static final double CANONICAL_TARGET_WEIGHT = 100.0;
  private static final double CANONICAL_L2 = 0.01;
  private static final double CANONICAL_EXCITATION_DAMPING = 0.1;
  private static final double CANONICAL_FRAME_DAMPING = 2.0;
  private static final double CANONICAL_ROTARY_DAMPING = 4.0;
  private static final double CANONICAL_MAX_STEP_S = 0.00025;
  private static final double CANONICAL_OPEN_GAP_MM = 0.0;

  private static class Params {
    String mode = null;
    double scale = Double.NaN;
    double freqHz = Double.NaN;
    double ampP2PMm = Double.NaN;
    double massExp = CANONICAL_MASS_EXP;
    double inertiaExp = CANONICAL_INERTIA_EXP;
    double forceExp = Double.NaN;
    double forceMultiplier = Double.NaN;
    double durationS = CANONICAL_DURATION_S;
    double settleS = CANONICAL_SETTLE_S;
    double targetWeight = CANONICAL_TARGET_WEIGHT;
    double l2Regularization = CANONICAL_L2;
    double excitationDamping = CANONICAL_EXCITATION_DAMPING;
    double frameDamping = CANONICAL_FRAME_DAMPING;
    double rotaryDamping = CANONICAL_ROTARY_DAMPING;
    double maxStepS = CANONICAL_MAX_STEP_S;
    double openGapMm = CANONICAL_OPEN_GAP_MM;
    String gravityState = "disabled";
    String outCsv = null;
    boolean verbose = false;

    double massMultiplier = Double.NaN;
    double inertiaMultiplier = Double.NaN;
    int nForceScaled = 0;
    String targetMarkerName = "";
    boolean collisionApiSuccess = false;
    int collisionBehaviorsDisabled = 0;
    int tmjConnectorsFound = 0;
    int tmjConnectorsModified = 0;
    boolean restLengthsReset = false;
    int nRestLengthsReset = 0;
    int nExciters = 0;
    boolean hybridSolvesDisabled = false;
    boolean inputProbesRemoved = false;
    boolean outputProbesRemoved = false;
    boolean geometryScaled = false;
    String modelUnits = "";
  }

  private static String requireValue(String[] args, int index, String flag) {
    if (index + 1 >= args.length) {
      throw new IllegalArgumentException("Missing value after " + flag);
    }
    return args[index + 1];
  }

  private static Params parseArgs(String[] args) {
    Params p = new Params();
    for (int i = 0; i < args.length; i++) {
      String a = args[i];
      if (a.equals("--mode")) {
        p.mode = requireValue(args, i, a); i++;
      }
      else if (a.equals("--scale")) {
        p.scale = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--freq_hz") || a.equals("--freq")) {
        p.freqHz = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--amp_p2p_mm") || a.equals("--amp_mm")) {
        p.ampP2PMm = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--mass_exp") || a.equals("--massExp")) {
        p.massExp = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--inertia_exp") || a.equals("--inertiaExp")) {
        p.inertiaExp = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--force_exp") || a.equals("--forceScaleExp")) {
        p.forceExp = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--force_multiplier") || a.equals("--forceScale")) {
        p.forceMultiplier = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--duration_s") || a.equals("--duration")) {
        p.durationS = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--settle_s") || a.equals("--settle")) {
        p.settleS = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--target_weight") || a.equals("--weight")) {
        p.targetWeight = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--l2_regularization") || a.equals("--l2")) {
        p.l2Regularization = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--excitation_damping") || a.equals("--damp")) {
        p.excitationDamping = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--frame_damping")) {
        p.frameDamping = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--rotary_damping")) {
        p.rotaryDamping = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--max_step_s")) {
        p.maxStepS = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--open_gap_mm")) {
        p.openGapMm = Double.parseDouble(requireValue(args, i, a)); i++;
      }
      else if (a.equals("--gravity")) {
        p.gravityState = requireValue(args, i, a); i++;
      }
      else if (a.equals("--out")) {
        p.outCsv = requireValue(args, i, a); i++;
      }
      else if (a.equals("--verbose")) {
        p.verbose = true;
      }
      else {
        throw new IllegalArgumentException("Unknown model argument: " + a);
      }
    }
    validateParams(p);
    return p;
  }

  private static boolean close(double a, double b) {
    double tol = Math.max(1e-12, 1e-10 * Math.max(Math.abs(a), Math.abs(b)));
    return Math.abs(a - b) <= tol;
  }

  private static void requireFinitePositive(double value, String label) {
    if (!Double.isFinite(value) || value <= 0) {
      throw new IllegalArgumentException(label + " must be finite and >0; got " + value);
    }
  }

  private static boolean inCanonicalScaleGrid(double value) {
    for (int i = 0; i <= 8; i++) {
      if (close(value, 0.80 + 0.05 * i)) return true;
    }
    return false;
  }

  private static boolean inCanonicalFrequencyGrid(double value) {
    for (int i = 0; i <= 18; i++) {
      if (close(value, 1.0 + 0.5 * i)) return true;
    }
    return false;
  }

  private static void validateParams(Params p) {
    if (!("fixed_force".equals(p.mode) || "force_capacity_s2".equals(p.mode))) {
      throw new IllegalArgumentException("--mode must be fixed_force or force_capacity_s2");
    }
    requireFinitePositive(p.scale, "scale");
    requireFinitePositive(p.freqHz, "frequency");
    requireFinitePositive(p.ampP2PMm, "peak-to-peak amplitude");
    if (!inCanonicalScaleGrid(p.scale)) {
      throw new IllegalArgumentException("scale is outside canonical 0.80:0.05:1.20 grid: " + p.scale);
    }
    if (!inCanonicalFrequencyGrid(p.freqHz)) {
      throw new IllegalArgumentException("frequency is outside canonical 1.0:0.5:10.0 grid: " + p.freqHz);
    }
    if (!(close(p.ampP2PMm, 1.0) || close(p.ampP2PMm, 1.5))) {
      throw new IllegalArgumentException("amplitude must be 1.0 or 1.5 mm peak-to-peak");
    }
    if (!close(p.massExp, CANONICAL_MASS_EXP) || !close(p.inertiaExp, CANONICAL_INERTIA_EXP)) {
      throw new IllegalArgumentException("canonical mass/inertia exponents are 3 and 5");
    }
    if (!close(p.durationS, CANONICAL_DURATION_S) || !close(p.settleS, CANONICAL_SETTLE_S)) {
      throw new IllegalArgumentException("canonical duration/settling are 4.0/0.5 s");
    }
    if (!close(p.targetWeight, CANONICAL_TARGET_WEIGHT) ||
        !close(p.l2Regularization, CANONICAL_L2) ||
        !close(p.excitationDamping, CANONICAL_EXCITATION_DAMPING)) {
      throw new IllegalArgumentException("noncanonical tracking-controller parameter");
    }
    if (!close(p.frameDamping, CANONICAL_FRAME_DAMPING) ||
        !close(p.rotaryDamping, CANONICAL_ROTARY_DAMPING) ||
        !close(p.maxStepS, CANONICAL_MAX_STEP_S)) {
      throw new IllegalArgumentException("noncanonical damping or maximum time step");
    }
    if (!close(p.openGapMm, CANONICAL_OPEN_GAP_MM)) {
      throw new IllegalArgumentException("canonical open gap is 0 mm");
    }
    if (!"disabled".equals(p.gravityState)) {
      throw new IllegalArgumentException("canonical primary/sensitivity grids require gravity disabled");
    }
    if (p.outCsv == null || p.outCsv.trim().length() == 0) {
      throw new IllegalArgumentException("--out is required");
    }
    p.massMultiplier = Math.pow(p.scale, p.massExp);
    p.inertiaMultiplier = Math.pow(p.scale, p.inertiaExp);
    double expectedExp = "fixed_force".equals(p.mode) ? 0.0 : 2.0;
    double expectedMultiplier = "fixed_force".equals(p.mode) ? 1.0 : Math.pow(p.scale, 2.0);
    if (!Double.isFinite(p.forceExp)) p.forceExp = expectedExp;
    if (!Double.isFinite(p.forceMultiplier)) p.forceMultiplier = expectedMultiplier;
    if (!close(p.forceExp, expectedExp) || !close(p.forceMultiplier, expectedMultiplier)) {
      throw new IllegalArgumentException("force scaling does not match selected canonical mode");
    }
  }

  private static FrameMarker findMarkerWithName(ModelComponent root, String name) {
    if (root instanceof FrameMarker) {
      FrameMarker fm = (FrameMarker)root;
      if (fm.getName() != null && fm.getName().equalsIgnoreCase(name)) return fm;
    }
    if (root instanceof CompositeComponent) {
      CompositeComponent cc = (CompositeComponent)root;
      for (int i = 0; i < cc.numComponents(); i++) {
        FrameMarker result = findMarkerWithName(cc.get(i), name);
        if (result != null) return result;
      }
    }
    return null;
  }

  private static RigidBody findRigidBodyWithName(ModelComponent root, String name) {
    if (root instanceof RigidBody) {
      RigidBody rb = (RigidBody)root;
      if (rb.getName() != null && rb.getName().equalsIgnoreCase(name)) return rb;
    }
    if (root instanceof CompositeComponent) {
      CompositeComponent cc = (CompositeComponent)root;
      for (int i = 0; i < cc.numComponents(); i++) {
        RigidBody result = findRigidBodyWithName(cc.get(i), name);
        if (result != null) return result;
      }
    }
    return null;
  }

  private static void applyMassAndInertiaScaling(RigidBody body, Params p) {
    double m0 = body.getMass();
    SymmetricMatrix3d j0 = new SymmetricMatrix3d(body.getRotationalInertia());
    Point3d com0 = new Point3d(body.getCenterOfMass());
    SymmetricMatrix3d j = new SymmetricMatrix3d(j0);
    j.scale(p.inertiaMultiplier);
    body.setInertia(m0 * p.massMultiplier, j, com0);
  }

  private static Double invokeGetterDouble(Object obj, String methodName) {
    try {
      java.lang.reflect.Method m = obj.getClass().getMethod(methodName);
      Object val = m.invoke(obj);
      if (val instanceof Number) return Double.valueOf(((Number)val).doubleValue());
    }
    catch (Exception e) {
      // Try next API name.
    }
    return null;
  }

  private static boolean invokeSetterDouble(Object obj, String methodName, double value) {
    try {
      java.lang.reflect.Method m = obj.getClass().getMethod(methodName, double.class);
      m.invoke(obj, Double.valueOf(value));
      return true;
    }
    catch (Exception e) {
      return false;
    }
  }

  private static Object tryGetMaterial(Object obj) {
    try {
      java.lang.reflect.Method m = obj.getClass().getMethod("getMaterial");
      return m.invoke(obj);
    }
    catch (Exception e) {
      return null;
    }
  }

  private static int touchForceMethodPair(
      Object obj, String getter, String setter, double multiplier, String label,
      IdentityHashMap<Object, Double> scaledStorage) {
    Double oldValue = invokeGetterDouble(obj, getter);
    if (oldValue == null || !Double.isFinite(oldValue.doubleValue())) return 0;

    if (scaledStorage.containsKey(obj)) {
      double expected = scaledStorage.get(obj).doubleValue();
      double tol = Math.max(1e-10, Math.abs(expected) * 1e-8);
      if (Math.abs(oldValue.doubleValue() - expected) > tol) {
        throw new RuntimeException("Shared force-capacity storage changed unexpectedly for " + label);
      }
      System.out.println(String.format(Locale.US,
          "[MandibleScalingInverseDDK_CURRENT] force-capacity %s shares already scaled storage via %s/%s: %.9g",
          label, getter, setter, oldValue.doubleValue()));
      return 1;
    }

    double expected = oldValue.doubleValue() * multiplier;
    if (!invokeSetterDouble(obj, setter, expected)) return 0;
    Double observed = invokeGetterDouble(obj, getter);
    double tol = Math.max(1e-10, Math.abs(expected) * 1e-8);
    if (observed == null || !Double.isFinite(observed.doubleValue()) ||
        Math.abs(observed.doubleValue() - expected) > tol) {
      throw new RuntimeException("Force-capacity setter readback failed for " + label +
          " via " + getter + "/" + setter);
    }
    scaledStorage.put(obj, observed);
    System.out.println(String.format(Locale.US,
        "[MandibleScalingInverseDDK_CURRENT] force-capacity %s via %s/%s: %.9g -> %.9g",
        label, getter, setter, oldValue.doubleValue(), observed.doubleValue()));
    return 1;
  }

  private static int touchMuscleForceCapacity(
      Object muscleLike, double multiplier, String label,
      IdentityHashMap<Object, Double> scaledStorage) {
    String[][] methodPairs = new String[][] {
      {"getMaxForce", "setMaxForce"},
      {"getMaxIsoForce", "setMaxIsoForce"},
      {"getMaximumForce", "setMaximumForce"},
      {"getMaxMuscleForce", "setMaxMuscleForce"},
      {"getOptForce", "setOptForce"},
      {"getMaxIsoForceN", "setMaxIsoForceN"}
    };
    for (int i = 0; i < methodPairs.length; i++) {
      int n = touchForceMethodPair(
          muscleLike, methodPairs[i][0], methodPairs[i][1], multiplier, label, scaledStorage);
      if (n > 0) return n;
    }
    Object material = tryGetMaterial(muscleLike);
    if (material != null) {
      String materialLabel = label + ".material(" + material.getClass().getSimpleName() + ")";
      for (int i = 0; i < methodPairs.length; i++) {
        int n = touchForceMethodPair(
            material, methodPairs[i][0], methodPairs[i][1], multiplier, materialLabel, scaledStorage);
        if (n > 0) return n;
      }
    }
    return 0;
  }

  private static int applyForceCapacitySensitivity(MechModel mech, Params p) {
    if ("fixed_force".equals(p.mode)) return 0;
    IdentityHashMap<Object, Double> scaledStorage = new IdentityHashMap<Object, Double>();
    int nMuscles = 0;
    for (AxialSpring spring : mech.axialSprings()) {
      if (spring instanceof ExcitationComponent) {
        String name = spring.getName() == null ? spring.getClass().getSimpleName() : spring.getName();
        nMuscles += touchMuscleForceCapacity(spring, p.forceMultiplier, name, scaledStorage);
      }
    }
    for (MultiPointSpring spring : mech.multiPointSprings()) {
      if ((spring instanceof ExcitationComponent) || (spring instanceof MultiPointMuscle)) {
        String name = spring.getName() == null ? spring.getClass().getSimpleName() : spring.getName();
        nMuscles += touchMuscleForceCapacity(spring, p.forceMultiplier, name, scaledStorage);
      }
    }
    if (nMuscles <= 0) {
      throw new RuntimeException("force_capacity_s2 found no muscle maximum-force parameters");
    }
    return nMuscles;
  }

  private static boolean invokeNoArg(Object obj, String methodName) {
    try {
      java.lang.reflect.Method m = obj.getClass().getMethod(methodName);
      m.invoke(obj);
      return true;
    }
    catch (Exception e) {
      return false;
    }
  }

  private static void requireDefaultCollisionDisabled(
      MechModel mech, Collidable.Group group0, Collidable.Group group1,
      String label) {
    CollisionBehavior behavior = mech.getDefaultCollisionBehavior(group0, group1);
    if (behavior == null) {
      throw new RuntimeException(
          "No default collision behavior was available for " + label);
    }
    if (behavior.isEnabled()) {
      throw new RuntimeException(
          "Default collision behavior remained enabled for " + label);
    }
  }

  private static void disableCollisions(MechModel mech, Params p) {
    // ArtiSynth stores the four reserved default behaviors in the same
    // CollisionBehaviorList as pair-specific overrides. Consequently,
    // numBehaviors() is expected to equal numDefaultPairs() after
    // clearCollisionBehaviors(); it is not expected to be zero.
    int defaultCount = mech.getCollisionManager().numDefaultPairs();
    int totalBefore = mech.getCollisionManager().numBehaviors();
    if (defaultCount <= 0 || totalBefore < defaultCount) {
      throw new RuntimeException(
          "Invalid collision-manager behavior counts before clearing: defaults="
          + defaultCount + ", total=" + totalBefore);
    }
    int overrideCount = totalBefore - defaultCount;

    mech.clearCollisionBehaviors();
    mech.clearCollisionResponses();

    int totalAfter = mech.getCollisionManager().numBehaviors();
    if (totalAfter != defaultCount) {
      throw new RuntimeException(
          "Pair-specific collision behaviors remained after clearCollisionBehaviors(): "
          + "expected " + defaultCount + " reserved defaults, found " + totalAfter);
    }
    if (mech.getCollisionManager().numResponses() != 0) {
      throw new RuntimeException(
          "Collision responses remained after clearCollisionResponses(): found "
          + mech.getCollisionManager().numResponses());
    }

    mech.setDefaultCollisionBehavior(false, 0.0);
    requireDefaultCollisionDisabled(
        mech, Collidable.Rigid, Collidable.Rigid, "Rigid-Rigid");
    requireDefaultCollisionDisabled(
        mech, Collidable.Rigid, Collidable.Deformable, "Rigid-Deformable");
    requireDefaultCollisionDisabled(
        mech, Collidable.Deformable, Collidable.Deformable,
        "Deformable-Deformable");
    requireDefaultCollisionDisabled(
        mech, Collidable.Deformable, Collidable.Self, "Deformable-Self");

    p.collisionApiSuccess = true;
    // Count the four verified disabled defaults plus all pair-specific
    // overrides that were removed from the inherited model.
    p.collisionBehaviorsDisabled = defaultCount + overrideCount;
  }

  private Object findTmjConnector(JawModel jm, String side) {
    String[] rootPaths = new String[] {
      "models/jawmodel/rigidBodyConnectors/" + side + "TMJ",
      "models/jawmodel/bodyConnectors/" + side + "TMJ"
    };
    for (int i = 0; i < rootPaths.length; i++) {
      Object value = findComponent(rootPaths[i]);
      if (value != null) return value;
    }
    String[] localPaths = new String[] {
      "rigidBodyConnectors/" + side + "TMJ",
      "bodyConnectors/" + side + "TMJ"
    };
    for (int i = 0; i < localPaths.length; i++) {
      Object value = jm.findComponent(localPaths[i]);
      if (value != null) return value;
    }
    return null;
  }

  private static boolean setUnilateralFalse(Object connector) {
    try {
      java.lang.reflect.Method setter = connector.getClass().getMethod("setUnilateral", boolean.class);
      setter.invoke(connector, Boolean.FALSE);
      try {
        java.lang.reflect.Method getter = connector.getClass().getMethod("isUnilateral");
        Object value = getter.invoke(connector);
        if (value instanceof Boolean && ((Boolean)value).booleanValue()) return false;
      }
      catch (Exception e) {
        // Setter success is the available verification in this API version.
      }
      return true;
    }
    catch (Exception directFailure) {
      try {
        java.lang.reflect.Method getProperty = connector.getClass().getMethod("getProperty", String.class);
        Object property = getProperty.invoke(connector, "unilateral");
        if (property == null) return false;
        java.lang.reflect.Method set = property.getClass().getMethod("set", Object.class);
        set.invoke(property, Boolean.FALSE);
        return true;
      }
      catch (Exception propertyFailure) {
        return false;
      }
    }
  }

  private void configureTmj(JawModel jm, Params p) {
    String[] sides = new String[] {"L", "R"};
    for (int i = 0; i < sides.length; i++) {
      Object connector = findTmjConnector(jm, sides[i]);
      if (connector != null) {
        p.tmjConnectorsFound++;
        if (setUnilateralFalse(connector)) p.tmjConnectorsModified++;
      }
    }
    if (p.tmjConnectorsFound != 2 || p.tmjConnectorsModified != 2) {
      throw new RuntimeException("Expected and modified two TMJ connectors; found=" +
          p.tmjConnectorsFound + " modified=" + p.tmjConnectorsModified);
    }
  }

  private static FrameMarker findLowerIncisor(JawModel jm, MechModel mech) {
    String[] paths = new String[] {"markers/LI", "markers/li", "frameMarkers/LI", "frameMarkers/li"};
    for (int i = 0; i < paths.length; i++) {
      ModelComponent value = jm.findComponent(paths[i]);
      if (value instanceof FrameMarker) return (FrameMarker)value;
    }
    String[] names = new String[] {
      "LI", "li", "lowerincisor", "lowerIncisor", "LowerIncisor",
      "lower_incisor", "Lower_Incisor", "lincisor", "LIncisor"
    };
    for (int i = 0; i < names.length; i++) {
      FrameMarker result = findMarkerWithName(jm, names[i]);
      if (result != null) return result;
    }
    for (FrameMarker marker : mech.frameMarkers()) {
      String name = marker.getName();
      if (name == null) continue;
      String lower = name.toLowerCase(Locale.US);
      if (lower.equals("li") ||
          (lower.contains("lower") && lower.contains("incisor")) ||
          (lower.contains("incisor") && !lower.contains("upper"))) return marker;
    }
    return null;
  }

  private static class TargetUpdater extends ControllerBase {
    private final TargetPoint target;
    private final Point3d basePosition;
    private final double amplitudeP2PUnits;
    private final double frequencyHz;
    private final double settleS;
    private final double openGapUnits;

    TargetUpdater(TargetPoint target, Point3d basePosition, double amplitudeP2PUnits,
                  double frequencyHz, double settleS, double openGapUnits) {
      this.target = target;
      this.basePosition = new Point3d(basePosition);
      this.amplitudeP2PUnits = amplitudeP2PUnits;
      this.frequencyHz = frequencyHz;
      this.settleS = settleS;
      this.openGapUnits = openGapUnits;
    }

    @Override
    public void apply(double t0, double t1) {
      double t = t1;
      Point3d position = new Point3d(basePosition);
      Vector3d velocity = new Vector3d();
      if (t >= settleS) {
        double tau = t - settleS;
        double omega = 2.0 * Math.PI * frequencyHz;
        position.z += 0.5 * amplitudeP2PUnits * (Math.sin(omega * tau) - 1.0)
            - openGapUnits;
        velocity.set(0.0, 0.0,
            0.5 * amplitudeP2PUnits * omega * Math.cos(omega * tau));
      }
      else {
        velocity.setZero();
      }
      target.setPosition(position);
      target.setVelocity(velocity);
    }
  }

  private static String csvEscape(String value) {
    if (value == null) return "";
    if (value.indexOf(',') >= 0 || value.indexOf('"') >= 0 ||
        value.indexOf('\n') >= 0 || value.indexOf('\r') >= 0) {
      return "\"" + value.replace("\"", "\"\"") + "\"";
    }
    return value;
  }

  private static class MetricsCollector extends ControllerBase {
    private final FrameMarker source;
    private final TargetPoint target;
    private final ArrayList<ExcitationComponent> exciters;
    private final Params p;
    private final double unitToMm;

    private double sumSquaredError = 0.0;
    private int n = 0;
    private double sourceZMin = Double.POSITIVE_INFINITY;
    private double sourceZMax = Double.NEGATIVE_INFINITY;
    private double targetZMin = Double.POSITIVE_INFINITY;
    private double targetZMax = Double.NEGATIVE_INFINITY;
    private double summedSquaredExcitation = 0.0;
    private double peakAbsoluteExcitation = 0.0;
    private boolean wrote = false;

    MetricsCollector(FrameMarker source, TargetPoint target,
                     ArrayList<ExcitationComponent> exciters, Params p,
                     boolean modelUnitsAreMm) {
      this.source = source;
      this.target = target;
      this.exciters = exciters;
      this.p = p;
      this.unitToMm = modelUnitsAreMm ? 1.0 : 1000.0;
    }

    @Override
    public void apply(double t0, double t1) {
      if (wrote) return;
      double t = t1;
      if (t >= p.settleS && t <= p.durationS) {
        Point3d current = source.getPosition();
        Point3d desired = target.getPosition();
        double errorMm = current.distance(desired) * unitToMm;
        sumSquaredError += errorMm * errorMm;
        n++;
        sourceZMin = Math.min(sourceZMin, current.z);
        sourceZMax = Math.max(sourceZMax, current.z);
        targetZMin = Math.min(targetZMin, desired.z);
        targetZMax = Math.max(targetZMax, desired.z);
        double sampleSum = 0.0;
        for (ExcitationComponent exciter : exciters) {
          double excitation = exciter.getExcitation();
          sampleSum += excitation * excitation;
          peakAbsoluteExcitation = Math.max(peakAbsoluteExcitation, Math.abs(excitation));
        }
        summedSquaredExcitation += sampleSum;
      }
      if (t >= p.durationS) {
        writeCsv();
        wrote = true;
      }
    }

    private void writeCsv() {
      if (n <= 0) throw new RuntimeException("No post-settling metric samples were collected");
      double rmse = Math.sqrt(sumSquaredError / n);
      double sourceP2PMm = (sourceZMax - sourceZMin) * unitToMm;
      double targetP2PMm = (targetZMax - targetZMin) * unitToMm;
      double gain = sourceP2PMm / targetP2PMm;
      double meanSumSquaredExcitation = summedSquaredExcitation / n;
      double[] finiteValues = new double[] {
        rmse, sourceP2PMm, targetP2PMm, gain,
        peakAbsoluteExcitation, meanSumSquaredExcitation
      };
      for (int i = 0; i < finiteValues.length; i++) {
        if (!Double.isFinite(finiteValues[i])) {
          throw new RuntimeException("Nonfinite metric at index " + i);
        }
      }

      File output = new File(p.outCsv).getAbsoluteFile();
      if (output.exists()) {
        throw new RuntimeException("Refusing to overwrite existing Java output: " + output);
      }
      File parent = output.getParentFile();
      if (parent != null && !parent.exists() && !parent.mkdirs()) {
        throw new RuntimeException("Could not create output directory: " + parent);
      }
      File temporary = new File(output.getPath() + ".tmp");
      if (temporary.exists() && !temporary.delete()) {
        throw new RuntimeException("Could not remove stale temporary output: " + temporary);
      }

      String header =
          "spec_version,mode,scale,freq_hz,target_amp_p2p_mm,mass_exp,inertia_exp," +
          "mass_multiplier,inertia_multiplier,force_exp,effective_force_multiplier," +
          "n_force_scaled,duration_s,settle_s,open_gap_mm,gravity_state,gravity_enabled," +
          "gravity_x,gravity_y,gravity_z,target_position_formula_id," +
          "target_velocity_formula_id,target_marker_name,controller_architecture_id," +
          "target_weight,l2_regularization,excitation_damping,frame_damping," +
          "rotary_damping,max_step_s,collision_setting,collision_api_success," +
          "collision_behaviors_disabled,tmj_joint_setting,tmj_connectors_found," +
          "tmj_connectors_modified,rest_lengths_reset,n_rest_lengths_reset,n_exciters," +
          "hybrid_solves_disabled,input_probes_removed,output_probes_removed," +
          "geometry_scaled,model_units,n_samples,actual_source_amp_p2p_mm," +
          "actual_target_amp_p2p_mm,amplitude_gain,tracking_rmse_mm,peak_excitation," +
          "mean_summed_squared_excitation\n";

      String row = String.format(Locale.US,
          "%s,%s,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d," +
          "%.17g,%.17g,%.17g,%s,false,0,0,0,%s,%s,%s,%s,%.17g,%.17g,%.17g," +
          "%.17g,%.17g,%.17g,disabled,%s,%d,unilateral_false,%d,%d,%s,%d,%d,%s,%s,%s," +
          "false,%s,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
          csvEscape(SPEC_VERSION), csvEscape(p.mode), p.scale, p.freqHz, p.ampP2PMm,
          p.massExp, p.inertiaExp, p.massMultiplier, p.inertiaMultiplier,
          p.forceExp, p.forceMultiplier, p.nForceScaled, p.durationS, p.settleS,
          p.openGapMm, csvEscape(p.gravityState), csvEscape(POSITION_FORMULA_ID),
          csvEscape(VELOCITY_FORMULA_ID), csvEscape(p.targetMarkerName),
          csvEscape(CONTROLLER_ARCHITECTURE_ID), p.targetWeight, p.l2Regularization,
          p.excitationDamping, p.frameDamping, p.rotaryDamping, p.maxStepS,
          Boolean.toString(p.collisionApiSuccess), p.collisionBehaviorsDisabled,
          p.tmjConnectorsFound, p.tmjConnectorsModified,
          Boolean.toString(p.restLengthsReset), p.nRestLengthsReset, p.nExciters,
          Boolean.toString(p.hybridSolvesDisabled),
          Boolean.toString(p.inputProbesRemoved),
          Boolean.toString(p.outputProbesRemoved), csvEscape(p.modelUnits), n,
          sourceP2PMm, targetP2PMm, gain, rmse, peakAbsoluteExcitation,
          meanSumSquaredExcitation);

      try (BufferedWriter writer = new BufferedWriter(new FileWriter(temporary))) {
        writer.write(header);
        writer.write(row);
      }
      catch (IOException e) {
        throw new RuntimeException("Could not write temporary Java output", e);
      }
      try {
        Files.move(temporary.toPath(), output.toPath(), StandardCopyOption.ATOMIC_MOVE);
      }
      catch (AtomicMoveNotSupportedException e) {
        try {
          Files.move(temporary.toPath(), output.toPath());
        }
        catch (IOException second) {
          throw new RuntimeException("Could not finalize Java output", second);
        }
      }
      catch (IOException e) {
        throw new RuntimeException("Could not finalize Java output", e);
      }
      if (p.verbose) {
        System.out.println("[MandibleScalingInverseDDK_CURRENT] wrote " + output);
      }
    }
  }

  /**
   * Resolves the inherited JawDemo working directory relative to the base
   * JawDemo class, not relative to this isolated CURRENT subclass.  The base
   * implementation passes {@code this} to ArtisynthPath, which makes an
   * isolated subclass resolve data/incisorForce below corrected_classes.
   */
  @Override
  public void setWorkingDir() {
    if (workingDirname == null) {
      return;
    }
    File workingDir = new File(
        ArtisynthPath.getSrcRelativePath(JawDemo.class, workingDirname));
    if (!workingDir.isDirectory()) {
      throw new RuntimeException(
          "Base JawDemo working directory is not a folder: " + workingDir);
    }
    ArtisynthPath.setWorkingDir(workingDir);
    if (debug) {
      System.out.println(
          "[MandibleScalingInverseDDK_CURRENT] working directory="
          + workingDir.getAbsolutePath());
    }
  }

  /**
   * Headless attach policy for the canonical rerun.
   *
   * <p>JawDemo.attach() calls setWorkingDir(), reloads incisorDispProbes.art,
   * and loads GUI control panels.  The canonical build deliberately removes
   * inherited probes and uses a headless play script, so calling the inherited
   * attach method would both undo the probe-removal invariant and make the
   * working-directory lookup depend on the isolated subclass location.</p>
   */
  @Override
  public void attach(DriverInterface driver) {
    setWorkingDir();
    // Deliberately do not call super.attach(driver), loadProbes(), or
    // loadControlPanel().  JawDemo.attach() itself does not call RootModel's
    // attach method, so this preserves the relevant lifecycle behavior while
    // keeping the canonical run probe-free and headless.
  }

  @Override
  public void build(String[] args) throws IOException {
    Params p = parseArgs(args);
    super.build(new String[0]);

    JawModel jm = (JawModel)findComponent("models/jawmodel");
    if (jm == null) throw new RuntimeException("Could not find JawModel at models/jawmodel");
    MechModel mech = jm;

    // The approved design has gravity disabled in both modes. There is no
    // gravity-enabled branch in this canonical class.
    mech.setGravity(0.0, 0.0, 0.0);
    mech.setFrameDamping(p.frameDamping);
    mech.setRotaryDamping(p.rotaryDamping);

    disableCollisions(mech, p);
    configureTmj(jm, p);

    p.inputProbesRemoved = invokeNoArg(this, "removeAllInputProbes");
    p.outputProbesRemoved = invokeNoArg(this, "removeAllOutputProbes");
    if (!p.inputProbesRemoved || !p.outputProbesRemoved) {
      throw new RuntimeException("Could not verify removal of inherited input/output probes");
    }

    mech.getSolver().setHybridSolvesEnabled(false);
    p.hybridSolvesDisabled = true;

    RigidBody jaw = null;
    ModelComponent direct = jm.findComponent("rigidBodies/jaw");
    if (direct instanceof RigidBody) jaw = (RigidBody)direct;
    if (jaw == null) jaw = findRigidBodyWithName(jm, "jaw");
    if (jaw == null) throw new RuntimeException("Could not find mandible rigid body named jaw");
    applyMassAndInertiaScaling(jaw, p);
    p.geometryScaled = false;

    FrameMarker lowerIncisor = findLowerIncisor(jm, mech);
    if (lowerIncisor == null) {
      StringBuilder names = new StringBuilder();
      for (FrameMarker marker : mech.frameMarkers()) {
        if (names.length() > 0) names.append(';');
        names.append(marker.getName());
      }
      throw new RuntimeException("Could not find lower-incisor marker; available=" + names.toString());
    }
    p.targetMarkerName = lowerIncisor.getName() == null ? "<unnamed>" : lowerIncisor.getName();

    Point3d basePosition = new Point3d(lowerIncisor.getPosition());
    double maxAbs = Math.max(Math.max(Math.abs(basePosition.x), Math.abs(basePosition.y)),
                             Math.abs(basePosition.z));
    boolean modelUnitsAreMm = maxAbs > 1.0;
    p.modelUnits = modelUnitsAreMm ? "mm" : "m";
    double mmToUnit = modelUnitsAreMm ? 1.0 : 0.001;

    TrackingController controller = new TrackingController(mech, "ddkTracker_CURRENT");
    ArrayList<ExcitationComponent> exciters = new ArrayList<ExcitationComponent>();
    int restCount = 0;
    for (AxialSpring spring : mech.axialSprings()) {
      spring.setRestLength(spring.getLength());
      restCount++;
      if (spring instanceof ExcitationComponent) {
        ExcitationComponent exciter = (ExcitationComponent)spring;
        controller.addExciter(exciter);
        exciters.add(exciter);
      }
    }
    for (MultiPointSpring spring : mech.multiPointSprings()) {
      spring.setRestLength(spring.getLength());
      restCount++;
      if (spring instanceof ExcitationComponent) {
        ExcitationComponent exciter = (ExcitationComponent)spring;
        controller.addExciter(exciter);
        exciters.add(exciter);
      }
      else if (spring instanceof MultiPointMuscle) {
        MultiPointMuscle muscle = (MultiPointMuscle)spring;
        controller.addExciter(muscle);
        exciters.add(muscle);
      }
    }
    p.nRestLengthsReset = restCount;
    p.restLengthsReset = restCount > 0;
    p.nExciters = exciters.size();
    if (!p.restLengthsReset || p.nExciters <= 0) {
      throw new RuntimeException("No spring rest lengths or excitation components available");
    }

    p.nForceScaled = applyForceCapacitySensitivity(mech, p);
    if ("fixed_force".equals(p.mode) && p.nForceScaled != 0) {
      throw new RuntimeException("fixed_force unexpectedly modified force capacity");
    }

    try {
      controller.setL2Regularization(p.l2Regularization);
    }
    catch (Exception e) {
      controller.addL2RegularizationTerm(p.l2Regularization);
    }
    controller.setExcitationDamping(p.excitationDamping);

    TargetPoint target = controller.addPointTarget(lowerIncisor, p.targetWeight);
    target.setPosition(new Point3d(basePosition));
    target.setVelocity(new Vector3d());

    double amplitudeUnits = p.ampP2PMm * mmToUnit;
    double openGapUnits = p.openGapMm * mmToUnit;
    addController(new TargetUpdater(target, basePosition, amplitudeUnits,
                                    p.freqHz, p.settleS, openGapUnits));
    addController(controller);
    addController(new MetricsCollector(lowerIncisor, target, exciters, p, modelUnitsAreMm));
    setMaxStepSize(p.maxStepS);

    System.out.println(String.format(Locale.US,
        "[MandibleScalingInverseDDK_CURRENT] mode=%s scale=%.2f f=%.1f A_p2p=%.1f " +
        "massMultiplier=%.9g inertiaMultiplier=%.9g forceMultiplier=%.9g nForceScaled=%d",
        p.mode, p.scale, p.freqHz, p.ampP2PMm, p.massMultiplier,
        p.inertiaMultiplier, p.forceMultiplier, p.nForceScaled));
  }
}
