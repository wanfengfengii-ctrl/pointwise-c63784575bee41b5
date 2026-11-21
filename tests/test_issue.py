import json
from dataclasses import replace

from issue.envelope import EnvelopeMismatch, open_envelope, seal_packet
from issue.packet import EvidencePayload
from tests.fixtures import DeskCase, scenario


def _single_pair_alternatives(packet):
    # These fixtures each have one possible public pair. Enumerate the only
    # two possible graph routes directly, without calling the review solver.
    costs = {(i, j): cost for i, j, cost in packet.evidence.edges}
    return {(): costs[(0, 2)], ((0, 0),): costs[(0, 1)] + costs[(1, 2)]}


class IssueTests(DeskCase):
    def test_fixed_excerpt(self):
        issued = self.exchange(('A', 'SOURCE_ONLY_MARKER', 'SOURCE_ONLY_MARKER'),
                               ('SOURCE_ONLY_MARKER', 'SOURCE_ONLY_MARKER', 'A'), (0, 0), (2, 2))
        self.close_source()
        received = self.receipts.get_received('case')
        self.assertEqual(received.packet, issued.packet)
        self.assertEqual(received.envelope, issued.envelope)
        body_text = json.loads(received.envelope)['body']
        data = json.loads(body_text)
        self.assertEqual(set(data), {'packet_id', 'old', 'new', 'evidence'})
        self.assertNotIn('SOURCE_ONLY_MARKER', body_text)
        for side_name in ('old', 'new'):
            side = data[side_name]
            self.assertEqual(set(side), {'identity', 'words'})
            self.assertEqual(set(side['identity']), {'manuscript_id', 'revision_id', 'excerpt_id', 'permission_id'})
            self.assertEqual(len(side['words']), 1)
            self.assertEqual(set(side['words'][0]), {'word_id', 'ordinal', 'value', 'segment_id', 'segment_order', 'word_index'})
        self.assertEqual(set(data['evidence']), {'nodes', 'edges'})
        self.assertEqual(data['evidence']['nodes'], [[0, 0]])
        self.assertTrue(all(type(n) is int for row in data['evidence']['edges'] for n in row))
        values = [data[side]['words'][0]['value'] for side in ('old', 'new')]
        origins = [(data[side]['words'][0]['segment_id'], data[side]['words'][0]['word_index']) for side in ('old', 'new')]
        self.assertEqual(values, ['A', 'A'])
        self.assertEqual(origins, [('old-segment', 0), ('new-segment', 2)])
        scenario('V3', {'old_public': [0], 'new_public': [2]}, ['A', 'A'], values,
                 [('old-segment', 0), ('new-segment', 2)], origins,
                 ['issue/publish.py', 'issue/envelope.py', 'issue/receipts.py'], 'Read the authorized slices and their offsets in the submitted segments.')

    def test_whole_revision_basis(self):
        self.exchange('AXX', 'XXA', (0, 0), (2, 2), name='long')
        self.exchange('A', 'A', name='short')
        self.close_source()
        long = self.receipts.get_received('long').packet
        short = self.receipts.get_received('short').packet
        self.assertEqual(_single_pair_alternatives(long), {(): 2, ((0, 0),): 4})
        self.assertEqual(_single_pair_alternatives(short), {(): 2, ((0, 0),): 0})

    def test_receive_reopen_and_conflicting_body(self):
        exchange = self.exchange('AXX', 'XXA', (0, 0), (2, 2))
        original = self.receipts.get_received('case')
        self.assertEqual(self.receipts.accept(exchange.envelope), original.receipt)
        self.close_source()
        self.close_offline()
        self.open_offline()
        self.assertEqual(self.receipts.accept(exchange.envelope), original.receipt)
        self.assertEqual(self.receipts.get_received('case'), original)
        altered = replace(exchange.packet, evidence=EvidencePayload(((0, 0),), ((0, 1, 2), (0, 2, 6), (1, 2, 2))))
        different_body = seal_packet(altered)
        self.assertEqual(open_envelope(different_body), altered)
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(different_body)
        self.assertEqual(self.receipts.get_received('case'), original)
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 1)

    def test_mismatched_envelope(self):
        first = self.exchange('A', 'A', name='first', receive=False)
        second = self.exchange('A', 'AA', name='second', receive=False)
        self.assertEqual(open_envelope(first.envelope), first.packet)
        self.assertEqual(open_envelope(second.envelope), second.packet)
        mixed, other = json.loads(first.envelope), json.loads(second.envelope)
        mixed.update(body=other['body'], sha256=other['sha256'])
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(json.dumps(mixed))
        reversed_declaration = json.loads(first.envelope)
        sides = reversed_declaration['declaration']
        sides['old'], sides['new'] = sides['new'], sides['old']
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(json.dumps(reversed_declaration))
        for packet_id in ('first', 'second'):
            self.assertIsNone(self.receipts.get_received(packet_id))
        size = self.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0]
        self.assertEqual(size, 0)
        scenario('V4', {'declaration': 'first', 'body': 'second'}, 0, size, None,
                 self.receipts.get_received('first'), ['issue/envelope.py', 'issue/receipts.py'],
                 'The two valid packet identities differ despite a valid body digest.')

    def test_corrupt_body(self):
        exchange = self.exchange('A', 'A', receive=False)
        outer = json.loads(exchange.envelope)
        outer['body'] += ' '
        with self.assertRaises(EnvelopeMismatch):
            self.receipts.accept(json.dumps(outer))
        self.assertIsNone(self.receipts.get_received('case'))
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM received_packets').fetchone()[0], 0)
