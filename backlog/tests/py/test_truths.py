# Copyright (C) 2026 FORKTEX S.R.L.
#
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-ForkTex-Commercial
#
# This file is part of ForkTex Python.
#
# For commercial licensing -- including use in proprietary products, SaaS
# deployments, or any context where AGPL obligations cannot be met -- you
# MUST obtain a commercial license from FORKTEX S.R.L. (info@forktex.com).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Tests for TruthsStore — per-domain knowledge persistence."""

import pytest

from forktex.agent.scraper.truths import TruthsStore


class TestTruthsStore:
    def test_load_nonexistent(self, temp_dir):
        store = TruthsStore(temp_dir)
        assert store.load("example.com") is None

    def test_save_and_load(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "selectors", "login_btn", "#login")
        data = store.load("example.com")
        assert data is not None
        assert data["domain"] == "example.com"
        entry = data["categories"]["selectors"]["login_btn"]
        assert entry["value"] == "#login"
        assert entry["confidence"] == 1.0
        assert entry["version"] == 1

    def test_save_multiple_categories(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "selectors", "btn", "#btn")
        store.save_entry("example.com", "xpaths", "title", "//h1")
        store.save_entry("example.com", "notes", "auth", "uses OAuth2")
        data = store.load("example.com")
        assert "btn" in data["categories"]["selectors"]
        assert "title" in data["categories"]["xpaths"]
        assert "auth" in data["categories"]["notes"]

    def test_invalid_category(self, temp_dir):
        store = TruthsStore(temp_dir)
        with pytest.raises(ValueError, match="Invalid category"):
            store.save_entry("example.com", "invalid_cat", "k", "v")

    def test_confidence(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "selectors", "btn", "#btn", confidence=0.7)
        data = store.load("example.com")
        assert data["categories"]["selectors"]["btn"]["confidence"] == 0.7

    def test_list_domains_empty(self, temp_dir):
        store = TruthsStore(temp_dir)
        assert store.list_domains() == []

    def test_list_domains(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "selectors", "a", "1")
        store.save_entry("other.org", "selectors", "b", "2")
        domains = store.list_domains()
        assert set(domains) == {"example.com", "other.org"}

    def test_versioning(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "selectors", "btn", "#v1")
        store.save_entry("example.com", "selectors", "btn", "#v2")
        data = store.load("example.com")
        entry = data["categories"]["selectors"]["btn"]
        assert entry["value"] == "#v2"
        assert entry["version"] == 2
        assert data["version"] == 2

    def test_overwrite_entry(self, temp_dir):
        store = TruthsStore(temp_dir)
        store.save_entry("example.com", "xpaths", "nav", "//nav[1]")
        store.save_entry("example.com", "xpaths", "nav", "//nav[@id='main']")
        data = store.load("example.com")
        assert data["categories"]["xpaths"]["nav"]["value"] == "//nav[@id='main']"
