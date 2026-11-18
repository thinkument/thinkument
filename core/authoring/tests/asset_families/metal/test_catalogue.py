from authoring_funneling.examples.metal.shared_rendering import catalogue

def test_generated_catalogue_matches_owned_metadata():
    assert (catalogue.STATIC_ROOT/'catalogue.js').read_text()==catalogue.browser_catalogue_source()
    catalogue.validate_browser_catalogue_v1()
