import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StackUpdateCheckTests(unittest.TestCase):
    def test_digest_pins_are_current_without_registry_requests(self):
        script_source = (ROOT / 'scripts/stack-update-check').read_text()
        check_function = script_source[
            script_source.index('check() {'):script_source.index('\nexport -f')
        ]
        shell_stubs = '''
docker() { echo "unexpected docker call: $*" >&2; return 1; }
platform_digest() { echo "unexpected registry request: $*" >&2; return 1; }
version_of() { echo "unexpected version request: $*" >&2; return 1; }
'''

        for image_reference in [
            'example.invalid/vpn@sha256:' + 'a' * 64,
            'example.invalid:5000/vpn:stable@sha256:' + 'b' * 64,
        ]:
            with self.subTest(image_reference=image_reference):
                image_check_result = subprocess.run(
                    ['bash', '-c', shell_stubs + check_function + '\ncheck "$IMAGE_REFERENCE"'],
                    env=dict(os.environ, IMAGE_REFERENCE=image_reference),
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(image_check_result.returncode, 0, image_check_result.stderr)
                self.assertEqual(image_check_result.stdout.strip(), f'current {image_reference}')
                self.assertEqual(image_check_result.stderr, '')

    def test_tagged_images_still_compare_platform_manifests(self):
        script_source = (ROOT / 'scripts/stack-update-check').read_text()
        check_function = script_source[
            script_source.index('check() {'):script_source.index('\nexport -f')
        ]
        shell_stubs = '''
docker() { echo 'example.invalid/vpn@sha256:local'; }
platform_digest() {
  case "$1" in
    example.invalid/vpn@sha256:local) echo old-platform ;;
    example.invalid/vpn:stable) echo "$REMOTE_DIGEST" ;;
    *) echo "unexpected manifest reference: $1" >&2; return 1 ;;
  esac
}
version_of() { if [ "${2:-}" = --remote ]; then echo 2; else echo 1; fi; }
'''

        for remote_digest, expected_output in [
            ('old-platform', 'current example.invalid/vpn:stable'),
            ('new-platform', 'update example.invalid/vpn:stable 1 2'),
        ]:
            with self.subTest(remote_digest=remote_digest):
                image_check_result = subprocess.run(
                    ['bash', '-c', shell_stubs + check_function + '\ncheck example.invalid/vpn:stable'],
                    env=dict(os.environ, REMOTE_DIGEST=remote_digest),
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(image_check_result.returncode, 0, image_check_result.stderr)
                self.assertEqual(image_check_result.stdout.strip(), expected_output)
                self.assertEqual(image_check_result.stderr, '')
