// Validazione P.IVA, CF, SDI in tempo reale
(function () {
    var RULES = [
        {
            sel: 'input[name="partita_iva"]',
            fn: function (v) { return /^\d{11}$/.test(v); },
            msg: 'P.IVA: deve essere esattamente 11 cifre numeriche',
            upper: false
        },
        {
            sel: 'input[name="codice_fiscale"]',
            fn: function (v) { return /^[A-Z0-9]{16}$/.test(v); },
            msg: 'CF: deve essere esattamente 16 caratteri alfanumerici',
            upper: true
        },
        {
            sel: 'input[name="codice_destinatario"]',
            fn: function (v) { return /^[A-Z0-9]{7}$/.test(v); },
            msg: 'Codice SDI: deve essere esattamente 7 caratteri alfanumerici',
            upper: true
        }
    ];

    function setup(inp, rule) {
        var hint = document.createElement('span');
        hint.className = 'val-hint';
        inp.parentNode.appendChild(hint);

        function check() {
            var raw = inp.value;
            if (rule.upper) {
                var pos = inp.selectionStart;
                inp.value = raw.toUpperCase();
                try { inp.setSelectionRange(pos, pos); } catch (e) {}
            }
            var v = inp.value.trim();
            if (!v) {
                inp.classList.remove('val-ok', 'val-err');
                hint.textContent = '';
                hint.className = 'val-hint';
                return true;
            }
            if (rule.fn(v)) {
                inp.classList.remove('val-err');
                inp.classList.add('val-ok');
                hint.className = 'val-hint val-hint-ok';
                hint.textContent = '✓ Formato valido';
                return true;
            }
            inp.classList.remove('val-ok');
            inp.classList.add('val-err');
            hint.className = 'val-hint val-hint-err';
            hint.textContent = '⚠ ' + rule.msg;
            return false;
        }

        inp.addEventListener('input', check);
        inp.addEventListener('blur', check);

        var form = inp.closest('form');
        if (form && !form._valBlocked) {
            form._valBlocked = true;
            form.addEventListener('submit', function (e) {
                var blocked = false;
                form.querySelectorAll('.val-err').forEach(function (el) {
                    if (el.value.trim()) blocked = true;
                });
                if (blocked) {
                    e.preventDefault();
                    var first = form.querySelector('.val-err');
                    if (first) {
                        first.focus();
                        first.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        RULES.forEach(function (rule) {
            document.querySelectorAll(rule.sel).forEach(function (inp) {
                setup(inp, rule);
            });
        });
    });
})();
