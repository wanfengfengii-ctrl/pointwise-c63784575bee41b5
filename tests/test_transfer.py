import json
import sqlite3
from contextlib import closing
from dataclasses import replace

from archive.read import read_report
from issue.delegation import parse_delegation
from issue.envelope import EnvelopeMismatch, open_envelope, seal_delegated_packet
from issue.packet import DelegatedPacket
from issue.publish import publish_delegated_packet
from issue.receipts import ReceiptStore
from review.confirmations import Confirmation
from review.requests import OldAnnotation, ReviewRequest
from review.resolve import NoCompatibleAlignment
from review.submit import submit_review
from tests.fixtures import DeskCase, scenario
from transfer_sample import SAMPLES


class TransferTests(DeskCase):
    def setUp(self):
        super().setUp()
        self.holder_connection = sqlite3.connect(':memory:')
        self.addCleanup(self.holder_connection.close)
        self.holder = ReceiptStore(self.holder_connection)
        self.holder.initialize()

    def _parent(self, name='late'):
        sample = next(item for item in SAMPLES if item['name'] == name)
        issued = self.exchange(tuple(sample['old_words']), tuple(sample['new_words']), name=name, receive=False)
        self.holder.accept(issued.envelope)
        return sample

    def _child(self, sample, *, packet_id='child', delegation=None, old_bounds=None, new_bounds=None):
        return publish_delegated_packet(
            self.holder, sample['name'], delegation if delegation is not None else sample['delegation'],
            old_bounds if old_bounds is not None else sample['old_bounds'],
            new_bounds if new_bounds is not None else sample['new_bounds'], packet_id=packet_id)

    def _receive(self, envelope, sample):
        return self.receipts.accept(envelope, delegation=sample['delegation'])

    def test_late_unconfirmed_and_confirmed(self):
        sample = self._parent('late')
        envelope = self._child(sample)
        self.close_source()
        receipt = self._receive(envelope, sample)
        self.assertEqual(receipt.packet_id, 'child')
        packet = self.receipts.get_received('child').packet
        self.assertIsInstance(packet, DelegatedPacket)
        self.assertEqual([word.value for word in packet.old.words], ['A'])
        self.assertEqual([word.value for word in packet.new.words], ['A'])
        outer = json.loads(envelope)
        self.assertEqual(outer['version'], 2)
        body = json.loads(outer['body'])
        self.assertEqual(set(body), {'packet_id', 'parent_packet_id', 'parent_body_digest', 'delegation_id',
                                     'delegation_digest', 'old', 'new', 'evidence'})
        self.assertEqual(set(outer['declaration']), {'packet_id', 'parent_packet_id', 'parent_body_digest',
                                                     'delegation_id', 'delegation_digest', 'old', 'new'})
        self.assertNotIn('X', outer['body'])
        self.assertEqual([word['segment_id'] for side in ('old', 'new') for word in body[side]['words']],
                         ['old-segment', 'new-segment'])
        annotation = OldAnnotation('a', packet.old.words[0].word_id)
        request = ReviewRequest('child', (annotation,))
        before = submit_review(self.receipts, self.archive, request)
        details = before.report.details
        self.assertEqual(details['cost'], 2)
        self.assertEqual(details['outcomes'][0]['targets'], [])
        self.assertTrue(details['outcomes'][0]['can_have_no_public_landing'])
        confirmation = Confirmation(packet.old.words[0].word_id, packet.new.words[0].word_id)
        after = submit_review(self.receipts, self.archive, ReviewRequest('child', (annotation,), (confirmation,)))
        details = after.report.details
        landings = [word['word_id'] for word in details['outcomes'][0]['targets']]
        self.assertEqual(details['cost'], 4)
        self.assertEqual(landings, ['late-new:2'])
        self.assertFalse(details['outcomes'][0]['can_have_no_public_landing'])
        expected_grant = {
            'parent_packet_id': sample['name'],
            'parent_body_digest': sample['delegation']['parent_body_digest'],
            'delegation_id': sample['delegation']['delegation_id'],
            'delegation_digest': parse_delegation(sample['delegation']).digest,
        }
        self.assertEqual(details['delegation'], expected_grant)
        scenario('V10', {'sample': 'late', 'confirmations': [[], ['late-old:0', 'late-new:2']]},
                 [(2, [], True), (4, ['late-new:2'], False)],
                 [(before.report.details['cost'], [], before.report.details['outcomes'][0]['can_have_no_public_landing']),
                  (after.report.details['cost'], landings, details['outcomes'][0]['can_have_no_public_landing'])],
                 [entry.receipt.receipt_id for entry in (before, after)],
                 [read_report(self.archive, entry.report.report_id).receipt.receipt_id for entry in (before, after)],
                 ['issue/publish.py', 'issue/alignment_evidence.py', 'issue/receipts.py'],
                 'The child keeps the parent fragment history in its gap costs.')

    def test_tie_landing_alternatives(self):
        sample = self._parent('tie')
        envelope = self._child(sample)
        self.close_source()
        self._receive(envelope, sample)
        packet = self.receipts.get_received('child').packet
        annotation = OldAnnotation('a', packet.old.words[0].word_id)
        request = ReviewRequest('child', (annotation,))
        before = submit_review(self.receipts, self.archive, request)
        self.assertEqual(before.report.details['cost'], 1)
        self.assertEqual([word['word_id'] for word in before.report.details['outcomes'][0]['targets']],
                         ['tie-new:0'])
        self.assertTrue(before.report.details['outcomes'][0]['can_have_no_public_landing'])
        confirmation = Confirmation(packet.old.words[0].word_id, packet.new.words[0].word_id)
        after = submit_review(self.receipts, self.archive, ReviewRequest('child', (annotation,), (confirmation,)))
        self.assertEqual(after.report.details['cost'], 1)
        self.assertEqual([word['word_id'] for word in after.report.details['outcomes'][0]['targets']],
                         ['tie-new:0'])
        self.assertFalse(after.report.details['outcomes'][0]['can_have_no_public_landing'])
        self.assertNotEqual(before.report.report_id, after.report.report_id)

    def test_issue_side_rejections(self):
        sample = self._parent('late')
        grant = sample['delegation']
        before = self.holder.get_received('late')
        invalid_grants = (
            {**grant, 'parent_packet_id': 'other'},
            {**grant, 'parent_body_digest': '0' * 64},
            {**grant, 'parent_body_digest': 'A' * 64},
            {**grant, 'old': {**grant['old'], 'revision_id': 'late-new'}},
            {**grant, 'new': {**grant['new'], 'last_word_id': 'late-new:9'}},
            {**grant, 'old': {key: value for key, value in grant['old'].items() if key != 'revision_id'}},
            {**grant, 'extra': True},
            'not-a-delegation',
        )
        for delegation in invalid_grants:
            with self.subTest(delegation=delegation), self.assertRaises(ValueError):
                self._child(sample, delegation=delegation)
        invalid_bounds = (
            (('late-old:1', 'late-old:1'), ('late-new:0', 'late-new:0')),
            (('late-old:0', 'late-old:0'), ('late-new:1', 'late-new:3')),
            (('late-old:2', 'late-old:2'), ('late-new:1', 'late-new:1')),
            (('late-old:1', 'late-old:0'), ('late-new:2', 'late-new:2')),
            ('late-old:0', ('late-new:2', 'late-new:2')),
        )
        for old_bounds, new_bounds in invalid_bounds:
            with self.subTest(old_bounds=old_bounds, new_bounds=new_bounds), self.assertRaises(ValueError):
                self._child(sample, old_bounds=old_bounds, new_bounds=new_bounds)
        with self.assertRaises(ValueError):
            self._child(sample, packet_id='late')
        self.assertEqual(self.holder.get_received('late'), before)
        self.assertIsNone(self.holder.get_received('child'))

    def test_whole_fragment_is_not_a_narrowing(self):
        sample = self._parent('late')
        full_grant = {
            'delegation_id': 'desk-late-full',
            'parent_packet_id': 'late',
            'parent_body_digest': sample['delegation']['parent_body_digest'],
            'old': {'revision_id': 'late-old', 'first_word_id': 'late-old:0', 'last_word_id': 'late-old:3'},
            'new': {'revision_id': 'late-new', 'first_word_id': 'late-new:0', 'last_word_id': 'late-new:3'},
        }
        with self.assertRaises(ValueError):
            self._child(sample, delegation=full_grant, old_bounds=('late-old:0', 'late-old:3'),
                        new_bounds=('late-new:0', 'late-new:3'))
        self.assertIsNone(self.holder.get_received('child'))

    def test_unknown_parent_and_foreign_delegation(self):
        sample = self._parent('late')
        other = next(item for item in SAMPLES if item['name'] == 'tie')
        envelope = self._child(sample)
        with self.assertRaises(ValueError):
            publish_delegated_packet(self.holder, 'absent', sample['delegation'],
                                     sample['old_bounds'], sample['new_bounds'])
        with self.assertRaises(ValueError):
            publish_delegated_packet(self.holder, 'late', other['delegation'],
                                     sample['old_bounds'], sample['new_bounds'])
        self.close_source()
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(envelope, delegation=other['delegation'])

    def test_reviewer_rejects_without_trusted_delegation(self):
        sample = self._parent('late')
        envelope = self._child(sample)
        self.close_source()
        for delegation in (None, {**sample['delegation'], 'parent_body_digest': '1' * 64},
                           {**sample['delegation'], 'delegation_id': 'desk-elsewhere'},
                           'not-a-delegation', sample['delegation']['old']):
            with self.subTest(delegation=delegation), self.assertRaises(EnvelopeMismatch):
                self.receipts.accept(envelope, delegation=delegation)
        self.assertIsNone(self.receipts.get_received('child'))
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 0)
        parent_envelope = self.holder.get_received('late').envelope
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(parent_envelope, delegation=sample['delegation'])
        self.assertIsNone(self.receipts.get_received('late'))

    def test_corrupt_or_rebound_child(self):
        sample = self._parent('late')
        envelope = self._child(sample)
        self.close_source()
        outer = json.loads(envelope)
        outer['body'] += ' '
        with self.assertRaises(EnvelopeMismatch):
            self._receive(json.dumps(outer), sample)
        packet = open_envelope(envelope)
        rebound = replace(packet, delegation_digest='f' * 64)
        with self.assertRaises(EnvelopeMismatch):
            self._receive(seal_delegated_packet(rebound), sample)
        over = json.loads(envelope)
        over['version'] = 3
        with self.assertRaises(EnvelopeMismatch):
            self._receive(json.dumps(over), sample)
        self.assertIsNone(self.receipts.get_received('child'))
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 0)

    def test_repost_same_body_and_conflicting_body(self):
        sample = self._parent('late')
        envelope = self._child(sample)
        original = self._receive(envelope, sample)
        self.assertEqual(self._receive(envelope, sample), original)
        self.close_source()
        self.close_offline()
        self.open_offline()
        self.assertEqual(self._receive(envelope, sample), original)
        self.assertEqual(self.receipts.get_received('child').receipt, original)
        conflicting = self._child(sample, packet_id='child', old_bounds=('late-old:0', 'late-old:0'),
                                  new_bounds=('late-new:1', 'late-new:1'))
        with self.assertRaises(EnvelopeMismatch):
            self._receive(conflicting, sample)
        self.assertEqual(self.receipts.get_received('child').receipt, original)

    def test_delegated_child_cannot_be_a_parent(self):
        sample = self._parent('late')
        envelope = self._child(sample)
        self.holder.accept(envelope, delegation=sample['delegation'])
        with self.assertRaises(ValueError):
            publish_delegated_packet(self.holder, 'child', sample['delegation'],
                                     sample['old_bounds'], sample['new_bounds'], packet_id='grandchild')
        self.assertIsNone(self.holder.get_received('grandchild'))

    def test_annotations_and_confirmations_stay_inside_child(self):
        sample = self._parent('late')
        self._receive(self._child(sample), sample)
        parent = self.holder.get_received('late').packet
        child = self.receipts.get_received('child').packet
        annotations = (OldAnnotation('a', parent.old.words[3].word_id),)
        for request in (ReviewRequest('child', annotations),
                        ReviewRequest('child', (OldAnnotation('a', child.old.words[0].word_id),),
                                      (Confirmation(parent.old.words[3].word_id, child.new.words[0].word_id),))):
            with self.subTest(request=request), self.assertRaises(ValueError):
                submit_review(self.receipts, self.archive, request)
        self.assertEqual(self.ledger_ids(), ([], []))

    def test_conflicting_confirmations_leave_no_entry(self):
        issued = self.exchange(('A', 'A'), ('A', 'A'), name='corners', receive=False)
        self.holder.accept(issued.envelope)
        digest = self.holder.get_received('corners').receipt.body_digest
        grant = {
            'delegation_id': 'desk-corners',
            'parent_packet_id': 'corners',
            'parent_body_digest': digest,
            'old': {'revision_id': 'corners-old', 'first_word_id': 'corners-old:0', 'last_word_id': 'corners-old:1'},
            'new': {'revision_id': 'corners-new', 'first_word_id': 'corners-new:0', 'last_word_id': 'corners-new:1'},
        }
        envelope = publish_delegated_packet(self.holder, 'corners', grant,
                                            ('corners-old:0', 'corners-old:0'),
                                            ('corners-new:0', 'corners-new:1'), packet_id='child')
        self.close_source()
        self.receipts.accept(envelope, delegation=grant)
        packet = self.receipts.get_received('child').packet
        annotations = (OldAnnotation('a', packet.old.words[0].word_id),)
        conflicting = (Confirmation(packet.old.words[0].word_id, packet.new.words[0].word_id),
                       Confirmation(packet.old.words[0].word_id, packet.new.words[1].word_id))
        with self.assertRaises(NoCompatibleAlignment):
            submit_review(self.receipts, self.archive, ReviewRequest('child', annotations, conflicting))
        self.assertEqual(self.ledger_ids(), ([], []))

    def test_delegated_sign_failure_leaves_no_entry(self):
        sample = self._parent('late')
        self._receive(self._child(sample), sample)
        self.offline.execute('CREATE TABLE failure_parent (id TEXT PRIMARY KEY)')
        self.offline.execute('''CREATE TABLE failure_child (
            id TEXT REFERENCES failure_parent(id) DEFERRABLE INITIALLY DEFERRED
        )''')
        self.offline.execute('''CREATE TRIGGER fail_archive_commit AFTER INSERT ON archive_receipts
            BEGIN INSERT INTO failure_child VALUES (NEW.report_id); END''')
        child = self.receipts.get_received('child').packet
        annotation = OldAnnotation('a', child.old.words[0].word_id)
        with self.assertRaises(sqlite3.IntegrityError):
            submit_review(self.receipts, self.archive, ReviewRequest('child', (annotation,)))
        self.assertEqual(self.ledger_ids(), ([], []))
        self.assertFalse(self.offline.in_transaction)
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM failure_child').fetchone()[0], 0)
