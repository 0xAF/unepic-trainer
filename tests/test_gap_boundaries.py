def test_page_aligned_site_includes_jump_instruction_length():
    from unepic_trainer.backend import find_near_gap
    from unepic_trainer.hooks import relative_jump
    cave = find_near_gap(0x90000000,[],4096)
    assert len(relative_jump(0x90000000,cave)) == 5
    assert cave == 0x10001000
