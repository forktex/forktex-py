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

"""Regression test: `forktex cloud connect` reads the JWT from
``token_resp.accessToken`` on the SDK's ``TokenResponse`` model.

The generated ``forktex_cloud.client.generated.TokenResponse`` exposes
``accessToken`` / ``refreshToken`` (camelCase, matching the OpenAPI
wire contract). If a contributor reverts to ``token_resp.access_token``
(snake_case), AttributeError silently propagates — connect succeeds at
the HTTP layer but the saved CloudContext gets ``access_token=None``,
and every subsequent /me request 401s.
"""

from __future__ import annotations

from forktex_cloud.client.generated import TokenResponse


def test_token_response_field_is_camel_case():
    tok = TokenResponse.model_validate(
        {"accessToken": "jwt-abc", "refreshToken": "rfr-xyz", "expiresIn": 3600}
    )
    assert tok.accessToken == "jwt-abc"
    assert tok.refreshToken == "rfr-xyz"
    assert not hasattr(tok, "access_token")


def test_connect_cloud_reads_camel_case_field():
    """The exact attribute access used in agent/auth/cli.py::connect_cloud."""
    tok = TokenResponse.model_validate(
        {"accessToken": "jwt-from-login", "expiresIn": 3600}
    )
    # Mirror agent/auth/cli.py — would raise AttributeError if someone
    # reverted to `.access_token`.
    access_token = tok.accessToken
    assert access_token == "jwt-from-login"
