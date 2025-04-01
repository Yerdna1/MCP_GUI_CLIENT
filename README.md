# MCP PyQt Klient (Slovenská verzia)

Grafický klient pre interakciu s MCP (Model Context Protocol) servermi pomocou PyQt6. Umožňuje pripojenie k viacerým serverom sekvenčne a interakciu s LLM modelmi (Ollama, Anthropic, Gemini) s podporou nástrojov (tools/function calling).

## Funkcie

*   **Sekvenčné pripojenie:** Automaticky sa pokúsi pripojiť ku všetkým povoleným MCP serverom definovaným v `mcp_config.json`.
*   **Podpora viacerých LLM:** Umožňuje výber medzi Ollama, Anthropic (Claude) a Google Gemini modelmi.
*   **Podpora nástrojov (Tool Use / Function Calling):** LLM modely môžu využívať nástroje poskytované pripojenými MCP servermi.
*   **Grafické rozhranie:** Prehľadné rozhranie postavené na PyQt6.
    *   Záložka pre manuálny výber a volanie nástrojov.
    *   Záložka pre chat s LLM.
    *   Konfigurácia API kľúčov pre Anthropic a Gemini.
    *   Stavový riadok zobrazujúci stav pripojenia.
    *   Príklady promptov pre jednoduchšie testovanie.

## Požiadavky

*   Python 3.10+
*   Docker (pre spustenie MCP serverov ako kontajnerov)
*   Git (pre klonovanie repozitára)
*   Požadované Python knižnice (viď `requreiments.txt`)

## Inštalácia a Nastavenie

1.  **Klonovanie Repozitára:**
    ```bash
    git clone https://github.com/Yerdna1/MCP_GUI_CLIENT.git
    cd MCP_GUI_CLIENT
    ```

2.  **Vytvorenie Virtuálneho Prostredia:**
    ```bash
    python -m venv .venv
    ```

3.  **Aktivácia Virtuálneho Prostredia:**
    *   Windows (Command Prompt/PowerShell):
        ```powershell
        .\.venv\Scripts\Activate.ps1
        # alebo
        .\.venv\Scripts\activate.bat
        ```
    *   macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```

4.  **Inštalácia Závislostí:**
    ```bash
    pip install -r requreiments.txt
    ```
    *(Poznámka: Názov súboru `requreiments.txt` obsahuje preklep.)*

5.  **Konfigurácia MCP Serverov (`mcp_config.json`):**
    *   Upravte súbor `mcp_config.json` podľa vašich potrieb.
    *   Definujte príkazy a argumenty pre spustenie vašich MCP serverov (napr. cez Docker).
    *   Uistite sa, že cesty k bind mountom v Docker príkazoch sú správne pre váš systém.
    *   **Dôležité:** Ak používate `github` server, nastavte `GITHUB_PERSONAL_ACCESS_TOKEN` ako systémovú environmentálnu premennú. Token bol odstránený z `mcp_config.json` z bezpečnostných dôvodov.

6.  **Konfigurácia API Kľúčov (v aplikácii):**
    *   Spustite aplikáciu.
    *   Prejdite na záložku "Chat with LLM".
    *   Kliknite na tlačidlo "Configure API Keys".
    *   Zadajte vaše API kľúče pre Anthropic a/alebo Google Gemini.
    *   Zaškrtnite "Save API key", ak si želáte kľúč uložiť pre budúce použitie (ukladá sa lokálne pomocou QSettings).

## Spustenie Aplikácie

Po aktivácii virtuálneho prostredia a konfigurácii spustite hlavný skript:

```bash
python improved_mcp_client.py
```
*(Poznámka: Predpokladá sa, že `improved_mcp_client.py` je hlavný spúšťací skript.)*

## Používanie

1.  **Pripojenie k Serverom:** Kliknite na tlačidlo "Connect All". Aplikácia sa pokúsi sekvenčne pripojiť ku všetkým povoleným serverom v `mcp_config.json`. Stav pripojenia sa zobrazí v stavovom riadku.
2.  **Manuálne Volanie Nástrojov:**
    *   Prejdite na záložku "Manual Tool Selection".
    *   Po úspešnom pripojení sa v ľavom paneli zobrazí zoznam dostupných nástrojov zoskupených podľa servera.
    *   Kliknite na nástroj pre zobrazenie jeho detailov a vstupného poľa pre argumenty.
    *   Zadajte argumenty v JSON formáte.
    *   Kliknite na "Execute Tool". Výsledok sa zobrazí v poli "Tool Results".
3.  **Chat s LLM:**
    *   Prejdite na záložku "Chat with LLM".
    *   Vyberte typ LLM (Ollama, Anthropic, Gemini) a konkrétny model z dropdown menu.
    *   Ak používate Anthropic alebo Gemini, uistite sa, že ste nakonfigurovali API kľúč.
    *   Použite príklady promptov alebo zadajte vlastnú správu do vstupného poľa.
    *   Kliknite na "Send" alebo stlačte Enter.
    *   LLM môže odpovedať priamo alebo požiadať o použitie nástroja. Ak použije nástroj, výsledok nástroja sa pošle späť LLM pre finálnu odpoveď.

## Štruktúra Projektu (Prehľad)

*   `.venv/`: Virtuálne prostredie Pythonu.
*   `src/`: Hlavný zdrojový kód.
    *   `client/`: Kód špecifický pre klienta (LLM handlery, konfigurácia, stav konverzácie).
    *   `server/`: Príklady MCP serverov (ak sú zahrnuté).
    *   `mcp_connector_fixed.py`: Hlavná logika pre správu MCP pripojení.
*   `ui/`: Kód pre grafické rozhranie (hlavné okno, widgety, dialógy, workery).
*   `mcp_config.json`: Konfigurácia MCP serverov.
*   `requreiments.txt`: Zoznam Python závislostí.
*   `improved_mcp_client.py`: Predpokladaný hlavný spúšťací skript.
*   `.gitignore`: Súbory a adresáre ignorované Gitom.
*   `README.md`: Tento súbor.

## Riešenie Problémov

*   **Chyby pripojenia:** Skontrolujte príkazy a cesty v `mcp_config.json`. Uistite sa, že Docker beží a obrazy pre MCP servery sú stiahnuté. Skontrolujte logy aplikácie pre detailnejšie informácie.
*   **Chyby API kľúčov:** Uistite sa, že ste správne zadali a uložili API kľúče cez dialóg "Configure API Keys". Pre GitHub server overte nastavenie environmentálnej premennej `GITHUB_PERSONAL_ACCESS_TOKEN`.
*   **Chyby LLM:** Skontrolujte logy pre chyby pri komunikácii s LLM API. Uistite sa, že vybraný model je dostupný a správne nakonfigurovaný (napr. Ollama musí bežať lokálne, ak používate lokálne modely).
*   **Chýbajúca knižnica `google.generativeai`:** Ak sa "gemini" nezobrazuje v dropdown menu aj po reštarte, skúste znova nainštalovať knižnicu priamo do virtuálneho prostredia: `.\.venv\Scripts\pip.exe install google-generativeai` (Windows) alebo `source .venv/bin/activate && pip install google-generativeai` (macOS/Linux).
