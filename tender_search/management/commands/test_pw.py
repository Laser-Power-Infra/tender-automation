# management/commands/test_pw.py

from django.core.management.base import BaseCommand
from playwright.sync_api import sync_playwright

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()

        print("Success")