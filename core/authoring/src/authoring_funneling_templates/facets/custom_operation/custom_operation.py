"""Copyable, host-owned JSONfnchainTM operation facet."""
from bindings2bindingsTM import Dict, Str
from authoring_funneling.b_typed_JSON_widget_declaration import (
    prepare_json_widget_v1,
)
from authoring_funneling.b_typed_JSON_widget_declaration.vocab_hub import (
    create_default_vocab,
)


def create_vocab():
    vocab = create_default_vocab()
    vocab.register(
        name='example.text.add_period',
        inputs=Dict({'text': Str}),
        output=Dict({'text': Str}),
        fn=lambda args, context: {'text': args['text'].rstrip('.') + '.'},
        version='1',
    )
    return vocab


def prepare_example(manifest):
    """Prepare the JSON widget against this process-owned extension."""
    return prepare_json_widget_v1(manifest, vocab=create_vocab())
