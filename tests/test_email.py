"""Targeted configuration, message and mocked SMTP tests; never sends internet mail."""
from dataclasses import replace
from datetime import datetime,timezone
import smtplib
import unittest
from unittest.mock import patch,MagicMock
from notifications.config import EmailConfig
from notifications.message import render
from notifications.notifier import smtp_send,category,backoff


def config(**kwargs):
    return replace(EmailConfig(enabled=True,sender='energy@example.test',recipient='viewer@example.test',run_id='email-test',building_id='house',source_id='meter'),**kwargs).validate()


def payload():
    return dict(episode_id='episode',run_id='email-test',building_id='<script>alert(1)</script>',source_id='meter',
        measurement_timestamp='2016-05-26T14:00:00',time_basis='dataset_naive',processed_at='2026-10-27T10:00:00+00:00',
        kind='individual',method='residual',energy_wh=380,interval_seconds=600,score=100,threshold=90)


class EmailTests(unittest.TestCase):
    def test_disabled_default_and_scope_mode(self):
        self.assertFalse(EmailConfig.from_env({}).enabled)
        for mode in ('individual','combined','both'):
            cfg=config(mode=mode)
            for kind in ('individual','combined'):
                self.assertEqual(cfg.accepts(kind,'email-test','house','meter'),mode in (kind,'both'))
            self.assertFalse(cfg.accepts('individual','old-run','house','meter'))
            self.assertFalse(cfg.accepts('individual','email-test','house','other'))

    def test_external_smtp_requires_separate_optin_tls_and_exact_scope(self):
        for kwargs in [dict(host='smtp.example.test'),dict(host='smtp.example.test',real_delivery=True),dict(host='smtp.example.test',security='starttls'),dict(run_id=''),dict(recipient='bad'),dict(sender='a@example.test\r\nBcc:x@example.test'),dict(username='secret',password='secret')]:
            with self.assertRaises(ValueError): config(**kwargs)
        self.assertTrue(config(host='smtp.example.test',real_delivery=True,security='ssl').enabled)
        self.assertNotIn('private-password',repr(config(security='ssl',username='private-user',password='private-password')))
        self.assertEqual(config().fingerprint,config(password='',username='').fingerprint)
        self.assertNotEqual(config().fingerprint,config(mode='both').fingerprint)

    def test_safe_ukrainian_multipart_historical_time_and_deterministic_message_id(self):
        row={'notification_id':'abc','recipient':'viewer@example.test','payload':payload()}
        msg=render(row,config(),datetime(2026,10,27,tzinfo=timezone.utc))
        plain=msg.get_body(preferencelist=('plain',)).get_content();html=msg.get_body(preferencelist=('html',)).get_content()
        self.assertIn('2016-05-26T14:00:00',plain);self.assertIn('часовий пояс не визначено',plain)
        self.assertIn('380 Wh / 10 хв',plain);self.assertIn('Experimental',plain);self.assertIn('не підтверджує',plain)
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertEqual(msg['Message-ID'],'<abc@energy-intelligence.local>')
        row['payload'].update(kind='combined',method='combined-q99-v1-unanimous',trigger_count=3,triggered_methods=['isolation_forest','autoencoder','residual'])
        self.assertIn('3/3',render(row,config(),datetime.now(timezone.utc)).get_body(preferencelist=('plain',)).get_content())

    def test_smtp_transports_are_mocked_and_secure(self):
        for security in ('none','starttls','ssl'):
            cfg=config(security=security)
            name='SMTP_SSL' if security=='ssl' else 'SMTP'
            with patch('notifications.notifier.smtplib.'+name) as factory:
                client=factory.return_value.__enter__.return_value;client.send_message.return_value={}
                smtp_send(MagicMock(),cfg)
                self.assertEqual(factory.call_args.kwargs['timeout'],10)
                if security=='starttls': client.starttls.assert_called_once()
                client.send_message.assert_called_once()

    def test_notifier_imports_no_ml_models(self):
        import subprocess,sys
        subprocess.run([sys.executable,'-c',"import notifications.notifier,sys; assert not any(x in sys.modules for x in ('torch','sklearn','integration.runtime'))"],check=True)

    def test_temporary_permanent_errors_and_bounded_backoff(self):
        for error,retry in [(smtplib.SMTPAuthenticationError(535,b'secret'),False),(smtplib.SMTPDataError(451,b'try'),True),
            (smtplib.SMTPDataError(550,b'no'),False),(TimeoutError(),True),(ValueError(),False),
            (smtplib.SMTPRecipientsRefused({'a':(450,b'try')}),True),(smtplib.SMTPRecipientsRefused({'a':(550,b'bad')}),False)]:
            self.assertEqual(category(error)[1],retry)
        self.assertEqual([backoff(i) for i in range(1,8)],[30,60,120,240,480,900,900])
