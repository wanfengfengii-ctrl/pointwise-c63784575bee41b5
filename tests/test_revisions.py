from excerpts.policy import PublicationPermission
from excerpts.selection import select_excerpt
from revisions.importer import import_revision
from revisions.model import SourceSegment
from tests.fixtures import DeskCase, scenario


class RevisionTests(DeskCase):
    def test_distinct_occurrences(self):
        old = import_revision(self.revisions, 'oral', 'oral-r1', (
            SourceSegment('opening', 2, ('A',)), SourceSegment('silence', 3, ()),
            SourceSegment('answer', 5, ('A',)),
        ))
        new = import_revision(self.revisions, 'oral', 'oral-r2', (SourceSegment('answer', 5, ('A',)),))
        expected = [('oral-r1:0', 'opening', 2, 0), ('oral-r1:1', 'answer', 5, 0)]
        actual = [(w.word_id, w.origin.segment_id, w.origin.segment_order, w.origin.word_index) for w in old.words]
        self.assertEqual(actual, expected)
        self.assertEqual(self.revisions.get('oral-r1'), old)
        self.assertEqual(self.revisions.get('oral-r2'), new)
        self.assertEqual(new.words[0].word_id, 'oral-r2:0')
        segments = [s.segment_id for s in self.revisions.get('oral-r1').segments]
        self.assertEqual(segments, ['opening', 'silence', 'answer'])
        scenario('V1', {'segments': [['A'], [], ['A']]}, expected, actual,
                 ['opening', 'silence', 'answer'], segments,
                 ['revisions/tokenize.py', 'revisions/store.py'], 'Count the two word occurrences in their original segments.')

    def test_invalid_import(self):
        original = import_revision(self.revisions, 'oral', 'r1', (SourceSegment('origin', 1, ('A',)),))
        invalid = (
            (SourceSegment('late', 2, ('A',)), SourceSegment('early', 1, ('B',))),
            (SourceSegment('s', 0, (None,)),),
            (SourceSegment('s', 0, ('',)),),
            (SourceSegment('s', 0, None),),
            (SourceSegment('s', 0, ('A',)), SourceSegment('s', 1, ('B',))),
        )
        for segments in invalid:
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                import_revision(self.revisions, 'oral', 'invalid', segments)
        with self.assertRaises(ValueError):
            import_revision(self.revisions, 'oral', 'r1', (SourceSegment('other', 0, ('B',)),))
        self.assertIsNone(self.revisions.get('invalid'))
        self.assertEqual(self.revisions.get('r1'), original)
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM source_words').fetchone()[0], 1)

    def test_reopen_initialization(self):
        revision = import_revision(self.revisions, 'oral', 'custom', (SourceSegment('user-segment', 0, ('user-word',)),))
        permission = PublicationPermission('user-permit', 'custom', 'custom:0', 'custom:0')
        excerpt = select_excerpt(self.revisions, self.excerpts, 'custom-excerpt', 'custom', permission, 'custom:0', 'custom:0')
        self.close_source()
        self.open_source()
        self.revisions.initialize()
        self.excerpts.initialize()
        self.assertEqual(self.revisions.get('custom'), revision)
        self.assertEqual(self.excerpts.get('custom-excerpt'), excerpt)
        binding = self.source.execute('SELECT revision_id, first_word_id, last_word_id FROM publication_permissions').fetchall()
        self.assertEqual(binding, [('custom', 'custom:0', 'custom:0')])

    def test_excerpt_permission(self):
        import_revision(self.revisions, 'oral', 'r1', (SourceSegment('speech', 4, ('A', 'B', 'C')),))
        permission = PublicationPermission('p', 'r1', 'r1:0', 'r1:1')
        with self.assertRaises(ValueError):
            select_excerpt(self.revisions, self.excerpts, 'bad', 'r1', permission, 'r1:1', 'r1:2')
        before = self.source.execute('SELECT COUNT(*) FROM excerpts').fetchone()[0]
        self.assertEqual(before, 0)
        self.assertIsNone(self.excerpts.get('bad'))
        accepted = select_excerpt(self.revisions, self.excerpts, 'good', 'r1', permission, 'r1:0', 'r1:1')
        values = [w.value for w in accepted.words]
        self.assertEqual(values, ['A', 'B'])
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM excerpts').fetchone()[0], 1)
        scenario('V2', {'revision': ['A', 'B', 'C'], 'permission': [0, 1], 'attempt': [1, 2]},
                 0, before, ['A', 'B'], values,
                 ['excerpts/policy.py', 'excerpts/selection.py', 'excerpts/store.py'], 'The requested end exceeds the closed permit by one word.')

    def test_foreign_endpoint_and_valid_projection(self):
        imported = import_revision(self.revisions, 'oral', 'r1', (
            SourceSegment('first', 1, ('A', 'B')), SourceSegment('second', 5, ('C',)),
        ))
        import_revision(self.revisions, 'other', 'r2', (SourceSegment('other', 1, ('A', 'B')),))
        permission = PublicationPermission('permit', 'r1', 'r1:0', 'r1:2')
        for start, end in (('r1:1', 'r2:1'), ('r1:2', 'r1:0'), ('r1:0', 'r1:3')):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                select_excerpt(self.revisions, self.excerpts, 'bad', 'r1', permission, start, end)
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM excerpts').fetchone()[0], 0)
        chosen = select_excerpt(self.revisions, self.excerpts, 'good', 'r1', permission, 'r1:1', 'r1:2')
        self.assertEqual([w.word_id for w in chosen.words], ['r1:1', 'r1:2'])
        self.assertEqual([w.origin for w in chosen.words], [imported.words[1].origin, imported.words[2].origin])
        self.assertEqual(self.excerpts.get('good'), chosen)

    def test_empty_revision_has_no_excerpt(self):
        import_revision(self.revisions, 'oral', 'r1', (SourceSegment('empty', 3, ()),))
        permission = PublicationPermission('permit', 'r1', 'r1:0', 'r1:0')
        with self.assertRaises(ValueError):
            select_excerpt(self.revisions, self.excerpts, 'bad', 'r1', permission, 'r1:0', 'r1:0')
        self.assertIsNone(self.excerpts.get('bad'))
