from uedcli import meshworld


class _FakeActor:
    def __init__(self, *, location=(0, 0, 0), props=()):
        self.location = location
        self.props = list(props)


class _FakeMesh:
    def __init__(self, *, origin=(0.0, 0.0, 0.0), rot_origin=(0, 0, 0), scale=(1.0, 1.0, 1.0)):
        self.origin = origin
        self.rot_origin = rot_origin
        self.scale = scale


def test_identity_everything_is_a_plain_translate():
    actor = _FakeActor(location=(100, 200, 0))
    mesh = _FakeMesh()
    world = meshworld.mesh_vertex_to_world((5, 0, 0), mesh=mesh, actor=actor)
    assert world == (105.0, 200.0, 0.0)


def test_mesh_rot_origin_90_yaw_rotates_in_mesh_local_frame_before_actor_placement():
    # RotOrigin = 90deg yaw (16384 uu); a mesh-local +X vertex should land along actor-local +Y
    # after Ro alone (actor Rotation identity, Location zero) -- this is the ComputerPublic case
    # the spike verified against UMesh::GetFrame.
    actor = _FakeActor(location=(0, 0, 0))
    mesh = _FakeMesh(rot_origin=(0, 16384, 0))
    world = meshworld.mesh_vertex_to_world((10, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0]) < 1e-6
    assert abs(world[1] - 10.0) < 1e-6

def test_actor_rotation_applies_outside_rot_origin_and_can_cancel_it():
    # CompB from the spike: actor Rotation = -90deg yaw exactly cancels a mesh RotOrigin of +90deg
    # yaw, restoring the mesh-local orientation in world space.
    actor = _FakeActor(location=(0, 0, 0), props=[("Rotation", "(Pitch=0,Yaw=-16384,Roll=0)")])
    mesh = _FakeMesh(rot_origin=(0, 16384, 0))
    world = meshworld.mesh_vertex_to_world((10, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0] - 10.0) < 1e-6
    assert abs(world[1]) < 1e-6


def test_prepivot_is_unrotated_unlike_the_brush_convention():
    # A rotated actor with PrePivot: PrePivot must be added UNROTATED (architecture.md D8 is the
    # OPPOSITE convention and must NOT be used here).
    actor = _FakeActor(location=(0, 0, 0),
                       props=[("Rotation", "(Pitch=0,Yaw=16384,Roll=0)"),   # +90deg yaw
                              ("PrePivot", "(X=5,Y=0,Z=0)")])
    mesh = _FakeMesh()
    world = meshworld.mesh_vertex_to_world((0, 0, 0), mesh=mesh, actor=actor)
    # PrePivot unrotated: world = Location + PrePivot + R*Ro*Scale*(v - Origin) = (0,0,0)+(5,0,0)+0
    assert abs(world[0] - 5.0) < 1e-6
    assert abs(world[1]) < 1e-6


def test_draw_scale_multiplies_mesh_scale():
    actor = _FakeActor(location=(0, 0, 0), props=[("DrawScale", "2.0")])
    mesh = _FakeMesh(scale=(1.0, 1.0, 1.0))
    world = meshworld.mesh_vertex_to_world((3, 0, 0), mesh=mesh, actor=actor)
    assert abs(world[0] - 6.0) < 1e-6


def test_actor_draw_scale_defaults_to_one():
    assert meshworld.actor_draw_scale(_FakeActor()) == 1.0


def test_actor_draw_scale_reads_prop():
    actor = _FakeActor(props=[("DrawScale", "2.5")])
    assert meshworld.actor_draw_scale(actor) == 2.5


def test_mesh_actor_linear_negative_draw_scale_flips_winding():
    from uedcli.transform import flip_winding
    actor = _FakeActor(props=[("DrawScale", "-1.0")])
    mesh = _FakeMesh()
    L = meshworld.mesh_actor_linear(mesh, actor)
    assert flip_winding(L) is True


def test_mesh_actor_linear_identity_does_not_flip_or_reject():
    from uedcli.transform import flip_winding, reject_degenerate
    actor = _FakeActor()
    mesh = _FakeMesh()
    L = meshworld.mesh_actor_linear(mesh, actor)
    assert flip_winding(L) is False
    reject_degenerate(L, "TestActor")  # must not raise


def test_all_zero_mesh_scale_is_read_as_unset_not_as_a_collapse():
    """A real stock mesh (`DeusExCharacters.SpiderBot2`) bakes `Scale=(0,0,0)`. Read literally it
    collapses the placement map to the zero matrix, which `reject_degenerate` refuses — aborting the
    whole photo over one decoration. Both `mesh_vertex_to_world` and `mesh_actor_linear` treat it as
    unset (identity), the same guard `meshrender.render_class` already applies."""
    from uedcli.transform import reject_degenerate
    actor = _FakeActor(location=(100, 0, 0))
    mesh = _FakeMesh(scale=(0.0, 0.0, 0.0))
    assert meshworld.mesh_vertex_to_world((5, 0, 0), mesh=mesh, actor=actor) == (105.0, 0.0, 0.0)
    L = meshworld.mesh_actor_linear(mesh, actor)
    reject_degenerate(L, "SpiderBot")            # must not raise
    assert L == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    # a genuine per-axis zero (only ONE axis) is still a real, degenerate scale — not masked
    flat = _FakeMesh(scale=(1.0, 1.0, 0.0))
    assert meshworld.mesh_actor_linear(flat, actor)[2][2] == 0.0


def test_apply_mesh_linear_matches_the_verified_per_vertex_reference():
    """The fast path (`mesh_actor_linear` + `mesh_actor_translation` once per actor, then
    `apply_mesh_linear` per vertex) must land every vertex exactly where the simple, independently
    verified `mesh_vertex_to_world` puts it — the regression that stops the hot loop silently
    diverging from the reference formula. Covers the same cases the reference tests above pin:
    identity, mesh RotOrigin, actor Rotation, unrotated PrePivot, DrawScale, and a mesh Origin."""
    cases = [
        (_FakeActor(location=(100, 200, 0)), _FakeMesh()),
        (_FakeActor(), _FakeMesh(rot_origin=(0, 16384, 0))),
        (_FakeActor(location=(0, 0, 0), props=[("Rotation", "(Pitch=0,Yaw=-16384,Roll=0)")]),
         _FakeMesh(rot_origin=(0, 16384, 0))),
        (_FakeActor(props=[("Rotation", "(Pitch=0,Yaw=16384,Roll=0)"), ("PrePivot", "(X=5,Y=0,Z=0)")]),
         _FakeMesh()),
        (_FakeActor(props=[("DrawScale", "2.0")]), _FakeMesh(scale=(1.5, 1.0, 0.5))),
        (_FakeActor(location=(7, -3, 11), props=[("Rotation", "(Pitch=4096,Yaw=12288,Roll=2048)")]),
         _FakeMesh(origin=(3.0, -2.0, 8.0), rot_origin=(1024, 16384, 512), scale=(1.0, 2.0, 0.5))),
    ]
    for actor, mesh in cases:
        L = meshworld.mesh_actor_linear(mesh, actor)
        translation = meshworld.mesh_actor_translation(actor)
        for v in ((0, 0, 0), (10, 0, 0), (-4, 7, 3), (2.5, -6.5, 1.5)):
            fast = meshworld.apply_mesh_linear(v, mesh_origin=mesh.origin, L=L,
                                               translation=translation)
            slow = meshworld.mesh_vertex_to_world(v, mesh=mesh, actor=actor)
            for i in range(3):
                assert abs(fast[i] - slow[i]) < 1e-9


def test_solve_uv_frame_reproduces_target_uv_at_all_three_vertices():
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)
    uv0, uv1, uv2 = (0.0, 0.0), (64.0, 0.0), (0.0, 64.0)
    frame = meshworld.solve_uv_frame(v0, v1, v2, uv0, uv1, uv2)
    assert frame is not None
    base, axis_u, axis_v, pan = frame

    def uv_at(p):
        rel = tuple(p[i] - base[i] for i in range(3))
        u = sum(rel[i] * axis_u[i] for i in range(3)) + pan[0]
        v = sum(rel[i] * axis_v[i] for i in range(3)) + pan[1]
        return (u, v)

    for p, expected in ((v0, uv0), (v1, uv1), (v2, uv2)):
        got = uv_at(p)
        assert abs(got[0] - expected[0]) < 1e-4
        assert abs(got[1] - expected[1]) < 1e-4


def test_solve_uv_frame_reproduces_uv_at_an_interior_point_too():
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)
    uv0, uv1, uv2 = (0.0, 0.0), (64.0, 0.0), (0.0, 64.0)
    base, axis_u, axis_v, pan = meshworld.solve_uv_frame(v0, v1, v2, uv0, uv1, uv2)
    midpoint = (5.0, 5.0, 0.0)   # not on the triangle, but still on its PLANE -- the frame must
                                  # hold everywhere on the plane, not just at the 3 vertices
    rel = tuple(midpoint[i] - base[i] for i in range(3))
    u = sum(rel[i] * axis_u[i] for i in range(3)) + pan[0]
    v = sum(rel[i] * axis_v[i] for i in range(3)) + pan[1]
    assert abs(u - 32.0) < 1e-4
    assert abs(v - 32.0) < 1e-4


def test_solve_uv_frame_degenerate_triangle_returns_none():
    # v2 collinear with v0/v1 -> zero area
    v0, v1, v2 = (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (20.0, 0.0, 0.0)
    assert meshworld.solve_uv_frame(v0, v1, v2, (0, 0), (1, 0), (2, 0)) is None
