from dataclasses import replace

from archive.read import read_report
from issue.envelope import seal_packet
from issue.packet import EvidencePayload, ExcerptIdentity, Packet, PacketWord, PublishedExcerpt
from review.confirmations import Confirmation
from review.requests import OldAnnotation, ReviewRequest
from review.resolve import NoCompatibleAlignment
from review.submit import submit_review
from tests.fixtures import DeskCase, scenario


def _outcomes(entry):
    return [([target['word_id'] for target in outcome['targets']], outcome['can_have_no_public_landing'])
            for outcome in entry.report.details['outcomes']]


class ReviewTests(DeskCase):
    def test_omitted_context(self):
        exchange = self.exchange('AXX', 'XXA', (0, 0), (2, 2))
        self.close_source()
        entry = submit_review(self.receipts, self.archive, exchange.request())
        actual = (entry.report.details['cost'], _outcomes(entry))
        expected = (2, [([], True)])
        self.assertEqual(actual, expected)
        saved = read_report(self.archive, entry.report.report_id)
        self.assertEqual(saved, entry)
        self.assertEqual(saved.receipt.packet_id, 'case')
        scenario('V5', {'old': list('AXX'), 'new': list('XXA'), 'public': ['A', 'A']}, expected, actual,
                 'case', saved.receipt.packet_id, ['issue/alignment_evidence.py', 'review/resolve.py', 'archive/read.py'],
                 'Matching both X occurrences costs two. Matching the A occurrences alone costs four.')

    def test_confirmation_changes_optimum(self):
        exchange = self.exchange('AXX', 'XXA', (0, 0), (2, 2))
        self.close_source()
        request = exchange.request()
        before = submit_review(self.receipts, self.archive, request)
        pair = Confirmation('case-old:0', 'case-new:2')
        confirmed = submit_review(self.receipts, self.archive, replace(request, confirmations=(pair, pair)))
        after = submit_review(self.receipts, self.archive, request)
        costs = [entry.report.details['cost'] for entry in (before, confirmed, after)]
        self.assertEqual(costs, [2, 4, 2])
        self.assertEqual(_outcomes(before), [([], True)])
        self.assertEqual(_outcomes(after), [([], True)])
        self.assertEqual(_outcomes(confirmed), [(['case-new:2'], False)])
        self.assertEqual(confirmed.report.details['confirmations'], [{'old_word_id': 'case-old:0', 'new_word_id': 'case-new:2'}])
        self.assertEqual(len({entry.report.report_id for entry in (before, confirmed, after)}), 3)
        self.assertEqual(read_report(self.archive, before.report.report_id), before)
        scenario('V6', {'confirmations': [[], ['case-old:0', 'case-new:2'], []]}, [2, 4, 2], costs,
                 [(['case-new:2'], False)], _outcomes(confirmed),
                 ['review/confirmations.py', 'review/resolve.py', 'review/submit.py'],
                 'Keeping the A pair forces all four X occurrences to remain unmatched.')

    def test_independently_built_evidence(self):
        old = PublishedExcerpt(ExcerptIdentity('oral', 'r1', 'e1', 'p1'), (PacketWord('r1:0', 0, 'A', 'intro', 0, 0),))
        new = PublishedExcerpt(ExcerptIdentity('oral', 'r2', 'e2', 'p2'), (PacketWord('r2:2', 2, 'A', 'intro', 0, 2),))
        # Bypass both public A positions at cost two, or take the pair with
        # two unmatched words on each side of it.
        manual = Packet('manual', old, new, EvidencePayload(((0, 0),), ((0, 1, 2), (0, 2, 2), (1, 2, 2))))
        self.close_source()
        self.receipts.accept(seal_packet(manual))
        request = ReviewRequest('manual', (OldAnnotation('annotation', 'r1:0'),))
        self.assertEqual(submit_review(self.receipts, self.archive, request).report.details['cost'], 2)
        confirmed = submit_review(self.receipts, self.archive, replace(request, confirmations=(Confirmation('r1:0', 'r2:2'),)))
        self.assertEqual(confirmed.report.details['cost'], 4)
        self.assertEqual(_outcomes(confirmed), [(['r2:2'], False)])

    def test_foreign_annotation_and_invalid_confirmations(self):
        first = self.exchange('A', 'A', name='first')
        second = self.exchange('A', 'A', name='second')
        self.close_source()
        good = submit_review(self.receipts, self.archive, first.request())
        self.assertEqual(_outcomes(good), [(['first-new:0'], False)])
        before = self.ledger_ids()
        for invalid in (replace(first.request(), annotations=second.request().annotations),
                        replace(first.request(), packet_id='unknown'),
                        replace(first.request(), confirmations=None),
                        first.request((Confirmation('first-old:0', ''),)),
                        first.request((Confirmation('first-old:0', 'second-new:0'),))):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                submit_review(self.receipts, self.archive, invalid)
        self.assertEqual(self.ledger_ids(), before)

    def test_hidden_target(self):
        exchange = self.exchange('AB', 'AB', (0, 0), (1, 1))
        self.close_source()
        entry = submit_review(self.receipts, self.archive, exchange.request())
        self.assertEqual(entry.report.details['cost'], 0)
        self.assertEqual(_outcomes(entry), [([], True)])

    def test_competing_confirmations(self):
        exchange = self.exchange('AA', 'A')
        self.close_source()
        result = submit_review(self.receipts, self.archive, exchange.request())
        expected = [(['case-new:0'], True), (['case-new:0'], True)]
        self.assertEqual(result.report.details['cost'], 1)
        self.assertEqual(_outcomes(result), expected)
        confirmations = (Confirmation('case-old:0', 'case-new:0'), Confirmation('case-old:1', 'case-new:0'))
        for i, confirmation in enumerate(confirmations):
            single = submit_review(self.receipts, self.archive, exchange.request((confirmation,)))
            self.assertEqual(single.report.details['cost'], 1)
            self.assertEqual(_outcomes(single)[i], (['case-new:0'], False))
            self.assertEqual(_outcomes(single)[1 - i], ([], True))
        before = self.ledger_ids()
        with self.assertRaises(NoCompatibleAlignment):
            submit_review(self.receipts, self.archive, exchange.request(confirmations))
        after = self.ledger_ids()
        self.assertEqual(after, before)
        scenario('V7', {'old': ['A', 'A'], 'new': ['A'], 'joint_target': 'case-new:0'}, expected,
                 _outcomes(result), [3, 3], [len(ids) for ids in after],
                 ['review/resolve.py', 'review/results.py', 'review/submit.py'],
                 'Either old A can use the one new position. Both cannot use it together.')

    def test_two_public_targets(self):
        exchange = self.exchange('A', 'AA')
        self.close_source()
        result = submit_review(self.receipts, self.archive, exchange.request())
        self.assertEqual(result.report.details['cost'], 1)
        self.assertEqual(_outcomes(result), [(['case-new:0', 'case-new:1'], False)])
        self.assertEqual([w['word_index'] for w in result.report.details['outcomes'][0]['targets']], [0, 1])

    def test_crossing_confirmations(self):
        exchange = self.exchange('AB', 'BA')
        self.close_source()
        matches = (Confirmation('case-old:0', 'case-new:1'), Confirmation('case-old:1', 'case-new:0'))
        with self.assertRaises(NoCompatibleAlignment):
            submit_review(self.receipts, self.archive, exchange.request(matches))
        self.assertEqual(self.ledger_ids(), ([], []))

    def test_multiple_compatible_confirmations(self):
        exchange = self.exchange('ABA', 'AABA')
        self.close_source()
        matches = (Confirmation('case-old:2', 'case-new:3'), Confirmation('case-old:0', 'case-new:1'))
        entry = submit_review(self.receipts, self.archive, exchange.request(matches))
        self.assertEqual(entry.report.details['cost'], 1)
        self.assertEqual(_outcomes(entry), [(['case-new:1'], False), (['case-new:2'], False), (['case-new:3'], False)])
