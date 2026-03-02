"""Quick check: extract and show first 5 emails from PST to see what data we're working with"""
import os
import sys

def main():
    # Ask user for PST path
    if len(sys.argv) > 1:
        pst_path = sys.argv[1]
    else:
        pst_path = input("Enter PST file path: ").strip()

    if not os.path.exists(pst_path):
        print(f"Error: File not found: {pst_path}")
        sys.exit(1)

    from import_pst_file import _init_pst_store, _iter_pst_payloads

    print(f"Loading PST: {pst_path}")
    print("="*80)

    try:
        namespace, target_store = _init_pst_store(pst_path, progress_callback=None)
        
        for i, payload in enumerate(_iter_pst_payloads(namespace, target_store), 1):
            if i > 5:  # Only show first 5
                break
            
            print(f"\n[Email {i}]")
            print(f"Subject: {payload.get('subject', '(no subject)')}")
            print(f"From: {payload.get('sender_name', '')} <{payload.get('sender_email', '')}>")
            print(f"Received: {payload.get('received_at', '')}")
            body = payload.get('body', '')
            if body:
                preview = body[:200].replace('\n', ' ')
                if len(body) > 200:
                    preview += "..."
                print(f"Body preview: {preview}")
            else:
                print("Body: (empty)")
            print("-"*80)
        
        print(f"\n✓ Showed first 5 emails from PST")
        
    except Exception as exc:
        print(f"Error: {exc}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
